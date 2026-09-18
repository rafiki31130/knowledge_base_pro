#!/usr/bin/env python3
"""Aspire un manuel d'un portail de documentation HTML vers une arborescence Markdown.

Conçu pour les portails de doc modernes (rendu côté serveur ou client), testé en
priorité sur la structure d'URL de `help.splunk.com`, mais sans sélecteur CSS en dur :
le conteneur de contenu est détecté par heuristique et reste surchargeable.

Deux phases séparées, pour pouvoir reconvertir sans re-télécharger :

    fetch   URLs -> cache HTML local
    render  cache HTML -> arborescence .md (liens internes réécrits)

Usage :
    splunk_help_to_md.py probe  <url>
    splunk_help_to_md.py crawl  <url-racine> --out ./out
    splunk_help_to_md.py crawl  <url-racine> --out ./out --render-only

Dépendances : requests, beautifulsoup4, markdownify (+ playwright si --mode browser).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

try:
    import requests
    from bs4 import BeautifulSoup, NavigableString, Tag
    from markdownify import MarkdownConverter
except ImportError as exc:  # pragma: no cover - message d'aide au démarrage
    sys.exit(f"Dépendance manquante ({exc.name}). "
             f"Installer : pip install requests beautifulsoup4 markdownify")

DEFAULT_UA = ("splunk-help-to-md/1.0 (documentation mirroring for offline personal use; "
              "contact: <your-email>)")

# Candidats de conteneur principal, du plus spécifique au plus large.
CONTENT_SELECTORS = [
    "main article", "article.content", "main .content", "main",
    "article", "[role=main]", "#main-content", ".main-content",
    "#content", ".content", ".markdown-body", ".doc-content",
]

# Éléments de chrome à retirer avant extraction (structurels + classes/id parlants).
STRIP_TAGS = ["script", "style", "noscript", "svg", "form", "button", "iframe",
              "nav", "header", "footer", "aside"]
STRIP_ATTR_RE = re.compile(
    r"(^|[-_ ])(nav|navbar|sidebar|side-bar|toc|table-of-contents|breadcrumb|"
    r"footer|masthead|cookie|consent|feedback|banner|announcement|"
    r"search|menu|skip-link|pagination|prev-next|social|share|rating)([-_ ]|$)",
    re.I)

# Extensions de « vrai fichier » en fin d'URL. Liste fermée à dessein : un test
# générique sur le dernier point prendrait un numéro de version (`.../9.4`) pour
# une extension, et casserait la résolution des liens relatifs de la page.
FILE_EXT_RE = re.compile(
    r"\.(html?|xhtml|php|aspx?|jsp|cgi|xml|json|pdf|txt|csv|md|zip|gz|tgz|"
    r"png|jpe?g|gif|svg|webp|ico|css|js|woff2?|ttf)$", re.I)

LANG_CLASS_RE = re.compile(r"(?:language|lang|highlight|brush|syntax)[-:]([a-z0-9+#]+)", re.I)
# Langues que l'on garde telles quelles pour l'annotation des blocs (cf. CONTRIBUTING).
KNOWN_LANGS = {"spl", "bash", "shell", "sh", "json", "xml", "yaml", "yml", "python",
               "ini", "conf", "text", "console", "powershell", "sql", "js", "regex"}


# --------------------------------------------------------------------------- #
# Utilitaires URL
# --------------------------------------------------------------------------- #

def normalize(url: str, keep_query: bool = False) -> str:
    """Canonicalise une URL : pas de fragment, pas de query, pas de slash final."""
    p = urlparse(url)
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme, p.netloc, path, "", p.query if keep_query else "", ""))


def link_base(url: str) -> str:
    """Base à donner à `urljoin` pour résoudre les liens relatifs d'une page.

    Les URLs de doc sont des chemins « répertoire » sans extension : le serveur
    résout `./voisin` sous la page courante, alors qu'`urljoin` sur une URL sans
    slash final le résout sous le parent — et perd un segment au passage.
    """
    p = urlparse(url)
    if p.path.endswith("/") or FILE_EXT_RE.search(p.path):
        return url
    return urlunparse((p.scheme, p.netloc, p.path + "/", p.params, p.query, ""))


def under_prefix(url: str, prefix: str) -> bool:
    """Vrai si `url` est la racine du manuel ou une page en dessous."""
    u, p = normalize(url), normalize(prefix)
    return u == p or u.startswith(p + "/")


def rel_md_path(url: str, prefix: str) -> Path:
    """Chemin .md miroir de l'URL, relatif à la racine de sortie."""
    u, p = normalize(url), normalize(prefix)
    if u == p:
        return Path("index.md")
    rest = u[len(p) + 1:]
    # Garde-fou : segments d'URL -> segments de chemin, sans traversée.
    parts = [re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-.") or "_"
             for s in rest.split("/") if s not in ("", ".", "..")]
    return Path(*parts[:-1], parts[-1] + ".md") if parts else Path("index.md")


# --------------------------------------------------------------------------- #
# Récupération
# --------------------------------------------------------------------------- #

@dataclass
class Fetcher:
    """Récupère du HTML, en statique (requests) ou via un navigateur (Playwright)."""

    mode: str = "auto"            # auto | static | browser
    delay: float = 1.0
    timeout: int = 30
    user_agent: str = DEFAULT_UA
    browser_executable: str | None = None
    robots: urllib.robotparser.RobotFileParser | None = None
    _session: requests.Session | None = field(default=None, init=False, repr=False)
    _browser: object | None = field(default=None, init=False, repr=False)
    _play: object | None = field(default=None, init=False, repr=False)
    _last: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.user_agent,
                                      "Accept": "text/html,application/xhtml+xml"})

    # -- politesse ---------------------------------------------------------- #
    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def allowed(self, url: str) -> bool:
        return self.robots.can_fetch(self.user_agent, url) if self.robots else True

    # -- navigateur --------------------------------------------------------- #
    def _ensure_browser(self):
        if self._browser is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                sys.exit("--mode browser demande Playwright : pip install playwright")
            self._play = sync_playwright().start()
            # `executable_path` sert quand les navigateurs Playwright sont fournis
            # par l'image/le poste plutôt que téléchargés par le paquet pip.
            launch: dict = {"headless": True}
            exe = self.browser_executable or os.environ.get("CHROMIUM_EXECUTABLE")
            if exe:
                launch["executable_path"] = exe
            self._browser = self._play.chromium.launch(**launch)
        return self._browser

    def _get_browser(self, url: str) -> tuple[int, str]:
        page = self._ensure_browser().new_page(user_agent=self.user_agent)
        try:
            resp = page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
            html = page.content()
            return (resp.status if resp else 0), html
        finally:
            page.close()

    # -- API ---------------------------------------------------------------- #
    def get(self, url: str) -> tuple[int, str]:
        """Retourne (status, html). Bascule en navigateur si le statique est vide."""
        self._throttle()
        if self.mode == "browser":
            return self._get_browser(url)

        r = self._session.get(url, timeout=self.timeout)
        # requests retombe sur ISO-8859-1 quand le header ne porte pas de charset :
        # sans ça, tout accent d'une page UTF-8 ressort en mojibake.
        if "charset" not in r.headers.get("content-type", "").lower():
            r.encoding = r.apparent_encoding or "utf-8"
        html = r.text if r.status_code == 200 else ""
        if self.mode == "auto" and r.status_code == 200 and not _looks_rendered(html):
            print(f"  [auto] contenu statique vide -> rendu navigateur : {url}",
                  file=sys.stderr)
            self.mode = "browser"
            return self._get_browser(url)
        return r.status_code, html

    def get_raw(self, url: str) -> bytes | None:
        """Téléchargement binaire (images), toujours en statique."""
        self._throttle()
        r = self._session.get(url, timeout=self.timeout)
        return r.content if r.status_code == 200 else None

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._play.stop()
        if self._session is not None:
            self._session.close()


def _looks_rendered(html: str) -> bool:
    """Le HTML brut porte-t-il déjà le corps du document, ou est-ce une coquille SPA ?

    On ne se fie pas à un simple seuil de longueur : une page de doc peut être
    légitimement courte. Le marqueur fiable d'une page rendue côté serveur, c'est
    la présence conjointe d'un titre et d'au moins un bloc de corps.
    """
    soup = BeautifulSoup(html, "html.parser")
    node, _ = pick_content(soup)
    if node is None:
        return False
    if len(node.get_text(strip=True)) >= RENDERED_CHARS:
        return True
    has_heading = node.find(["h1", "h2", "h3"]) is not None
    has_body = node.find(["p", "li", "pre", "table", "dl"]) is not None
    return has_heading and has_body


def load_robots(origin: str, fetcher: Fetcher) -> urllib.robotparser.RobotFileParser | None:
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = fetcher._session.get(urljoin(origin, "/robots.txt"), timeout=15)
        if r.status_code != 200:
            return None
        rp.parse(r.text.splitlines())
        return rp
    except requests.RequestException:
        return None


# --------------------------------------------------------------------------- #
# Découverte des URLs
# --------------------------------------------------------------------------- #

def urls_from_sitemap(origin: str, prefix: str, fetcher: Fetcher, depth: int = 0) -> set[str]:
    """Récupère les URLs du sitemap filtrées par préfixe (suit les sitemapindex)."""
    found: set[str] = set()
    if depth > 3:
        return found
    candidates = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"] if depth == 0 \
        else [origin]
    for cand in candidates:
        url = urljoin(origin, cand) if depth == 0 else cand
        try:
            r = fetcher._session.get(url, timeout=fetcher.timeout)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
        except (requests.RequestException, ET.ParseError):
            continue
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        for sm in root.findall(f"{ns}sitemap/{ns}loc"):
            if sm.text:
                found |= urls_from_sitemap(sm.text.strip(), prefix, fetcher, depth + 1)
        for loc in root.findall(f"{ns}url/{ns}loc"):
            if loc.text and under_prefix(loc.text.strip(), prefix):
                found.add(normalize(loc.text.strip()))
        if found:
            break
    return found


def crawl_links(start: str, prefix: str, fetcher: Fetcher, cache: "Cache",
                max_pages: int) -> list[str]:
    """Parcours en largeur limité au préfixe, en alimentant le cache au passage."""
    seen, queue, order = {normalize(start)}, [normalize(start)], []
    while queue and len(order) < max_pages:
        url = queue.pop(0)
        if not fetcher.allowed(url):
            print(f"  robots.txt interdit : {url}", file=sys.stderr)
            continue
        html = cache.get(url)
        if html is None:
            status, html = fetcher.get(url)
            if status != 200 or not html:
                print(f"  HTTP {status} : {url}", file=sys.stderr)
                continue
            cache.put(url, html)
            print(f"  [{len(order) + 1}] {url}")
        order.append(url)
        for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
            nxt = normalize(urljoin(link_base(url), a["href"]))
            if nxt not in seen and under_prefix(nxt, prefix):
                seen.add(nxt)
                queue.append(nxt)
    return order


# --------------------------------------------------------------------------- #
# Cache HTML
# --------------------------------------------------------------------------- #

class Cache:
    """Cache disque URL -> HTML, pour rendre `fetch` et `render` indépendants."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self.index: dict[str, str] = json.loads(self.index_path.read_text()) \
            if self.index_path.exists() else {}

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha1(normalize(url).encode()).hexdigest()

    def get(self, url: str) -> str | None:
        key = self.index.get(normalize(url))
        if not key:
            return None
        path = self.root / f"{key}.html"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def put(self, url: str, html: str) -> None:
        key = self._key(url)
        (self.root / f"{key}.html").write_text(html, encoding="utf-8")
        self.index[normalize(url)] = key
        self.index_path.write_text(json.dumps(self.index, indent=1, sort_keys=True))

    def urls(self) -> list[str]:
        return sorted(self.index)


# --------------------------------------------------------------------------- #
# Extraction du contenu
# --------------------------------------------------------------------------- #

def strip_chrome(soup: BeautifulSoup, extra_selectors: list[str]) -> None:
    for tag in soup.find_all(STRIP_TAGS):
        tag.decompose()
    for sel in extra_selectors:
        for tag in soup.select(sel):
            tag.decompose()
    for tag in soup.find_all(attrs={"class": True}):
        if STRIP_ATTR_RE.search(" ".join(tag.get("class", []))):
            tag.decompose()
    for tag in soup.find_all(attrs={"id": True}):
        if STRIP_ATTR_RE.search(tag.get("id", "")):
            tag.decompose()


MIN_CONTENT_CHARS = 80      # en-deçà, un conteneur sémantique reste suspect
RENDERED_CHARS = 200        # en-deçà, on soupçonne une page rendue côté client


def pick_content(soup: BeautifulSoup, selector: str | None = None) -> tuple[Tag | None, str]:
    """Retourne (nœud de contenu, sélecteur retenu)."""
    if selector:
        node = soup.select_one(selector)
        return node, selector
    # 1. premier sélecteur sémantique avec assez de texte
    fallback: tuple[Tag, str, int] | None = None
    for sel in CONTENT_SELECTORS:
        node = soup.select_one(sel)
        if not node:
            continue
        n = len(node.get_text(strip=True))
        if n >= MIN_CONTENT_CHARS:
            return node, sel
        if fallback is None or n > fallback[2]:
            fallback = (node, sel, n)
    # 2. sinon le plus fourni des sélecteurs sémantiques qui ont matché
    if fallback is not None and fallback[2] > 0:
        return fallback[0], f"{fallback[1]} (peu de texte)"
    # 3. repli : le bloc le plus dense en texte
    best, best_len = None, 0
    for node in soup.find_all(["div", "section", "body"]):
        n = len(node.get_text(strip=True))
        if n > best_len:
            best, best_len = node, n
    return best, "(heuristique densité)"


def page_title(node: Tag, soup: BeautifulSoup) -> str:
    h1 = node.find("h1") if node else None
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        return re.split(r"\s*[|·—-]\s*", soup.title.string.strip())[0]
    return "Sans titre"


# --------------------------------------------------------------------------- #
# Conversion Markdown
# --------------------------------------------------------------------------- #

class _Converter(MarkdownConverter):
    """markdownify avec les conventions du dépôt (titres ATX, puces `-`)."""


def extract_code_blocks(node: Tag) -> list[str]:
    """Remplace les <pre> par des marqueurs ; retourne les blocs fence correspondants."""
    blocks: list[str] = []
    for pre in node.find_all("pre"):
        classes = " ".join(pre.get("class", []))
        code = pre.find("code")
        if code:
            classes += " " + " ".join(code.get("class", []))
        m = LANG_CLASS_RE.search(classes)
        lang = m.group(1).lower() if m else ""
        if lang not in KNOWN_LANGS:
            lang = "spl" if lang in ("splunk", "splunk-spl") else ""
        text = (code or pre).get_text()
        text = text.replace("\r\n", "\n").strip("\n")
        fence = "````" if "```" in text else "```"
        blocks.append(f"{fence}{lang}\n{text}\n{fence}")
        marker = NavigableString(f"\n@@CODEBLOCK{len(blocks) - 1}@@\n")
        pre.replace_with(marker)
    return blocks


def restore_code_blocks(md: str, blocks: list[str]) -> str:
    def sub(m: re.Match) -> str:
        return blocks[int(m.group(1))]
    return re.sub(r"@@CODEBLOCK(\d+)@@", sub, md)


def rewrite_links(node: Tag, base_url: str, url_to_path: dict[str, str],
                  self_path: str) -> None:
    """Liens vers des pages aspirées -> chemins relatifs .md ; le reste -> absolu."""
    here = Path(self_path).parent
    for a in node.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "#")):
            continue
        absolute = urljoin(link_base(base_url), href)
        target = url_to_path.get(normalize(absolute))
        if target:
            rel = os.path.relpath(target, here).replace(os.sep, "/")
            anchor = urlparse(absolute).fragment
            a["href"] = f"./{rel}" if not rel.startswith(".") else rel
            if anchor:
                a["href"] += f"#{anchor}"
        else:
            a["href"] = absolute


def rewrite_images(node: Tag, base_url: str, assets: dict[str, str] | None,
                   self_path: str) -> list[tuple[str, str]]:
    """Absolutise les <img>. Si `assets` est fourni, planifie leur téléchargement."""
    planned: list[tuple[str, str]] = []
    here = Path(self_path).parent
    for img in node.find_all("img", src=True):
        absolute = urljoin(link_base(base_url), img["src"].strip())
        if assets is None:
            img["src"] = absolute
            continue
        name = assets.get(absolute)
        if name is None:
            ext = Path(urlparse(absolute).path).suffix[:5] or ".png"
            name = f"_assets/{hashlib.sha1(absolute.encode()).hexdigest()[:12]}{ext}"
            assets[absolute] = name
            planned.append((absolute, name))
        img["src"] = os.path.relpath(name, here).replace(os.sep, "/")
    return planned


def html_to_markdown(html: str, url: str, url_to_path: dict[str, str], self_path: str,
                     selector: str | None, strip_selectors: list[str],
                     assets: dict[str, str] | None) -> tuple[str, str, list[tuple[str, str]]]:
    """Retourne (titre, markdown, images à télécharger)."""
    soup = BeautifulSoup(html, "html.parser")
    strip_chrome(soup, strip_selectors)
    node, _ = pick_content(soup, selector)
    if node is None:
        return "Sans titre", "", []

    title = page_title(node, soup)
    # Le H1 devient le titre du fichier : on évite le doublon dans le corps.
    first_h1 = node.find("h1")
    if first_h1 and first_h1.get_text(strip=True) == title:
        first_h1.decompose()

    planned = rewrite_images(node, url, assets, self_path)
    rewrite_links(node, url, url_to_path, self_path)
    blocks = extract_code_blocks(node)

    md = _Converter(heading_style="ATX", bullets="-", strip=["button"]).convert_soup(node)
    md = restore_code_blocks(md, blocks)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return title, md, planned


def write_page(out: Path, rel: str, title: str, md: str, source: str) -> None:
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_title = title.replace('"', "'")
    header = (f'---\nsource: {source}\ntitle: "{safe_title}"\n'
              f"retrieved: {time.strftime('%Y-%m-%d')}\n---\n\n")
    path.write_text(f"{header}# {title}\n\n{md}\n", encoding="utf-8")


def write_summary(out: Path, pages: list[tuple[str, str]], root_url: str) -> None:
    """Index Markdown de l'arborescence produite (liens relatifs, cf. CONTRIBUTING)."""
    lines = ["# Sommaire", "",
             f"Miroir Markdown de <{root_url}>.",
             f"Généré le {time.strftime('%Y-%m-%d')} — {len(pages)} pages.", ""]
    def order(item: tuple[str, str]) -> tuple[str, ...]:
        # `welcome.md` doit précéder `welcome/...` : on compare sur les segments
        # d'URL, extension retirée, `index.md` (clé vide) en tête.
        parts = Path(item[0]).with_suffix("").parts
        return ("",) if parts == ("index",) else parts

    for rel, title in sorted(pages, key=order):
        depth = len(Path(rel).parts) - 1
        lines.append(f"{'  ' * depth}- [{title}](./{rel})")
    (out / "SOMMAIRE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #

def cmd_probe(args: argparse.Namespace) -> int:
    """Diagnostic : que voit le script sur une page ? Sert à régler --content-selector."""
    fetcher = Fetcher(mode=args.mode, delay=0, timeout=args.timeout,
                      user_agent=args.user_agent,
                      browser_executable=args.browser_executable)
    origin = f"{urlparse(args.url).scheme}://{urlparse(args.url).netloc}"
    rp = load_robots(origin, fetcher)
    print(f"robots.txt      : {'trouvé' if rp else 'absent/inaccessible'}", end="")
    if rp:
        print(f" — fetch autorisé : {rp.can_fetch(args.user_agent, args.url)}")
    else:
        print()

    status, html = fetcher.get(args.url)
    print(f"HTTP            : {status}  ({len(html)} octets)")
    print(f"mode effectif   : {fetcher.mode}")
    if status != 200 or not html:
        fetcher.close()
        return 1

    soup = BeautifulSoup(html, "html.parser")
    strip_chrome(soup, args.strip_selector)
    node, sel = pick_content(soup, args.content_selector)
    print(f"conteneur       : {sel}")
    print(f"texte extrait   : {len(node.get_text(strip=True)) if node else 0} caractères")
    print(f"titre           : {page_title(node, soup) if node else '-'}")
    if node:
        host = urlparse(args.url).netloc
        internal = sum(1 for a in node.find_all("a", href=True)
                       if urlparse(urljoin(link_base(args.url), a["href"])).netloc == host)
        print(f"liens même site : {internal} | <pre> : {len(node.find_all('pre'))} "
              f"| tables : {len(node.find_all('table'))}")
        _, md, _ = html_to_markdown(html, args.url, {}, "index.md",
                                    args.content_selector, args.strip_selector, None)
        print("\n--- aperçu Markdown (40 premières lignes) ---")
        print("\n".join(md.splitlines()[:40]))
    fetcher.close()
    return 0


def cmd_crawl(args: argparse.Namespace) -> int:
    root = normalize(args.url)
    prefix = normalize(args.prefix or args.url)
    out, cache = Path(args.out), Cache(Path(args.cache or Path(args.out) / ".cache"))
    origin = f"{urlparse(root).scheme}://{urlparse(root).netloc}"

    fetcher = Fetcher(mode=args.mode, delay=args.delay, timeout=args.timeout,
                      user_agent=args.user_agent,
                      browser_executable=args.browser_executable)
    if not args.render_only:
        if not args.ignore_robots:
            fetcher.robots = load_robots(origin, fetcher)
            if fetcher.robots and not fetcher.robots.can_fetch(args.user_agent, root):
                fetcher.close()
                sys.exit(f"robots.txt interdit {root} pour ce User-Agent. "
                         f"Arrêt (--ignore-robots pour passer outre, sous votre "
                         f"responsabilité).")
        print("== Découverte des URLs ==")
        urls = sorted(urls_from_sitemap(origin, prefix, fetcher))
        print(f"sitemap : {len(urls)} URLs sous le préfixe")
        print("== Récupération ==")
        if urls:
            for i, url in enumerate(urls[:args.max_pages], 1):
                if cache.get(url) is not None:
                    continue
                if not fetcher.allowed(url):
                    print(f"  robots.txt interdit : {url}", file=sys.stderr)
                    continue
                status, html = fetcher.get(url)
                if status == 200 and html:
                    cache.put(url, html)
                    print(f"  [{i}/{len(urls)}] {url}")
                else:
                    print(f"  HTTP {status} : {url}", file=sys.stderr)
        else:
            print("pas de sitemap exploitable -> parcours des liens")
            crawl_links(root, prefix, fetcher, cache, args.max_pages)

    urls = [u for u in cache.urls() if under_prefix(u, prefix)][:args.max_pages]
    if not urls:
        fetcher.close()
        sys.exit("Aucune page en cache : rien à convertir.")

    print(f"== Conversion ({len(urls)} pages) ==")
    url_to_path = {u: str(rel_md_path(u, prefix)) for u in urls}
    assets: dict[str, str] | None = {} if args.download_images else None
    pages, to_download = [], []
    for url in urls:
        html = cache.get(url)
        rel = url_to_path[url]
        title, md, planned = html_to_markdown(html, url, url_to_path, rel,
                                              args.content_selector, args.strip_selector,
                                              assets)
        if not md:
            print(f"  vide (conteneur non détecté) : {url}", file=sys.stderr)
            continue
        write_page(out, rel, title, md, url)
        to_download += planned
        pages.append((rel, title))

    if to_download:
        print(f"== Images ({len(to_download)}) ==")
        for src, name in to_download:
            target = out / name
            if target.exists():
                continue
            data = fetcher.get_raw(src)
            if data:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

    write_summary(out, pages, root)
    fetcher.close()
    print(f"\n{len(pages)} pages écrites dans {out}/ (index : {out}/SOMMAIRE.md)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("url", help="URL racine du manuel")
        sp.add_argument("--mode", choices=["auto", "static", "browser"], default="auto",
                        help="auto (défaut) bascule en navigateur si le HTML est vide")
        sp.add_argument("--timeout", type=int, default=30)
        sp.add_argument("--user-agent", default=DEFAULT_UA)
        sp.add_argument("--browser-executable",
                        default=os.environ.get("CHROMIUM_EXECUTABLE"),
                        help="binaire Chromium pour --mode browser "
                             "(défaut : $CHROMIUM_EXECUTABLE, sinon celui de Playwright)")
        sp.add_argument("--content-selector",
                        help="sélecteur CSS du contenu (sinon détection automatique)")
        sp.add_argument("--strip-selector", action="append", default=[],
                        help="sélecteur CSS à supprimer (répétable)")

    sp = sub.add_parser("probe", help="diagnostique une page sans rien écrire")
    common(sp)
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("crawl", help="aspire le manuel vers du Markdown")
    common(sp)
    sp.add_argument("--out", required=True, help="dossier de sortie")
    sp.add_argument("--prefix", help="préfixe d'URL à ne pas quitter (défaut : url)")
    sp.add_argument("--cache", help="cache HTML (défaut : <out>/.cache)")
    sp.add_argument("--delay", type=float, default=1.0,
                    help="délai entre requêtes, en secondes (défaut 1.0)")
    sp.add_argument("--max-pages", type=int, default=500)
    sp.add_argument("--render-only", action="store_true",
                    help="reconvertit depuis le cache, sans requête réseau")
    sp.add_argument("--download-images", action="store_true")
    sp.add_argument("--ignore-robots", action="store_true",
                    help="passe outre robots.txt (sous votre responsabilité)")
    sp.set_defaults(func=cmd_crawl)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

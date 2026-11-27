"""Rendered site: no root-absolute links outside the project subpath.

The site is a GitHub Pages project site served under /<repo>/ (the path of SITE_URL), so a
link like href="/assets/x.css" would point outside it and break. Links under the project
subpath are fine: Quarto writes 404.html that way on purpose, because Pages serves the 404
page at whatever URL was missing. Protocol-relative links ("//host/...") are not root paths.
"""

import os
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse, urlsplit

import pytest

from hazelnut.site.config import SITE_DIR, SITE_URL

RENDERED = SITE_DIR / "_site"
SITE_PATH = urlparse(SITE_URL).path.strip("/")  # "crop-markets"


def _pattern(site_path: str) -> re.Pattern:
    allowed = f"(?!{re.escape(site_path)}/)" if site_path else ""
    # href="/..." or src="/..." (either quote), not "//..." and not "/<site_path>/...".
    return re.compile(r"""\b(?:href|src)\s*=\s*["']/(?!/)""" + allowed + r"""[^"']*""", re.I)


def root_absolute_links(site_dir: Path, site_path: str = SITE_PATH) -> list[str]:
    """Every href/src in the HTML under `site_dir` that is root-absolute outside `site_path`."""
    pattern = _pattern(site_path)
    bad = []
    for path in sorted(Path(site_dir).rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in pattern.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            bad.append(f"{path.relative_to(site_dir).as_posix()}:{line}: {m.group(0)[:120]}")
    return bad


def test_site_path_comes_from_site_url():
    assert SITE_PATH == "crop-markets"


def test_link_check_on_a_tiny_site(tmp_path):
    good = (
        '<a href="hazelnut/index.html">x</a><link href="./site_libs/a.css">'
        '<script src="https://cdn.example/x.js"></script><img src="//cdn.example/i.png">'
        "<a href='/crop-markets/methods.html'>m</a><a href=\"#top\">t</a>"
        '<a href="/crop-markets/">root</a>'
    )
    (tmp_path / "index.html").write_text(good, encoding="utf-8")
    (tmp_path / "404.html").write_text('<a href="/crop-markets/index.html">home</a>', encoding="utf-8")
    assert root_absolute_links(tmp_path) == []

    sub = tmp_path / "hazelnut"
    sub.mkdir()
    (sub / "page.html").write_text(
        '<p>ok</p>\n<link href="/assets/site.css">\n<script src = \'/assets/site.js\'></script>\n'
        '<a href="/">home</a><a href="/crop-marketsX/no.html">trap</a><a HREF="/Up.html">u</a>',
        encoding="utf-8",
    )
    bad = root_absolute_links(tmp_path)
    assert len(bad) == 5
    assert bad[0].startswith("hazelnut/page.html:2: ")
    assert bad[1].startswith("hazelnut/page.html:3: ")
    assert any('"/crop-marketsX/no.html' in b for b in bad)


@pytest.mark.skipif(not RENDERED.is_dir(), reason="site/_site not rendered (run quarto render site)")
def test_rendered_site_has_no_root_absolute_links():
    assert (RENDERED / "404.html").is_file(), "404.html missing from the rendered site"
    bad = root_absolute_links(RENDERED)
    assert not bad, f"{len(bad)} root-absolute link(s) outside /{SITE_PATH}/:\n" + "\n".join(bad[:20])


METHODS_REF = re.compile(r"""href\s*=\s*["'][^"']*methods\.html#([^"']+)["']""", re.I)
ID_ATTR = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)


def missing_methods_anchors(site_dir: Path, skip: Path | None = None) -> list[str]:
    """Every `methods.html#id` link in the HTML under `site_dir` (but not under `skip`, the
    other language's tree) whose id is not in that tree's methods.html."""
    ids = set(ID_ATTR.findall((Path(site_dir) / "methods.html").read_text(encoding="utf-8")))
    bad = []
    for path in sorted(Path(site_dir).rglob("*.html")):
        if skip is not None and Path(skip) in path.parents:
            continue
        for anchor in METHODS_REF.findall(path.read_text(encoding="utf-8", errors="replace")):
            if anchor not in ids:
                bad.append(f"{path.relative_to(site_dir).as_posix()}: #{anchor}")
    return bad


def test_missing_methods_anchors_on_a_tiny_site(tmp_path):
    (tmp_path / "methods.html").write_text('<section id="sarima"></section>', encoding="utf-8")
    (tmp_path / "a.html").write_text(
        '<a href="../methods.html#sarima">ok</a><a href="methods.html#nope">bad</a>',
        encoding="utf-8")
    assert missing_methods_anchors(tmp_path) == ["a.html: #nope"]


@pytest.mark.skipif(not RENDERED.is_dir(), reason="site/_site not rendered (run quarto render site)")
def test_rendered_methods_links_point_at_existing_cards():
    tr = RENDERED / "tr"
    bad = missing_methods_anchors(RENDERED, skip=tr)
    if tr.is_dir():
        bad += [f"tr/{b}" for b in missing_methods_anchors(tr)]
    assert not bad, "methods.html anchors that do not exist:\n" + "\n".join(bad[:20])


# --- every internal link resolves, in both language trees --------------------------------

TR_TREE = "tr"
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)  # https:, mailto:, data:, javascript: ...


class _Links(HTMLParser):
    """href / src / data-href attribute values in document order, as (value, is_alternate).
    Script and style content is not parsed, so links inside JS strings are not counted."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, bool]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        alternate = tag == "link" and (a.get("rel") or "").lower() == "alternate"
        for name, value in attrs:
            if name in ("href", "src", "data-href") and value is not None:
                self.links.append((value, alternate))

    handle_startendtag = handle_starttag


def _target(site_dir: Path, page: Path, url: str, site_path: str) -> Path | None:
    """The file an internal link leads to; None for external, same-page and root links
    outside the project subpath (root_absolute_links reports those)."""
    url = url.strip()
    if not url or url.startswith(("#", "//")) or SCHEME.match(url):
        return None
    path = unquote(urlsplit(url).path)
    if path.startswith("/"):
        prefix = f"/{site_path}/" if site_path else "/"
        if not (path + "/").startswith(prefix):
            return None
        target = site_dir / path[len(prefix):]
    else:
        target = page.parent / path if path else page
    if path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return Path(os.path.normpath(target))


def link_problems(site_dir: Path, site_path: str = SITE_PATH) -> list[str]:
    """Internal links (href, src, and the language switch's data-href) under `site_dir`
    whose target file does not exist, and links from a Turkish page (site_dir/tr) that
    leave the Turkish tree. Only the hreflang alternates may cross to the other language."""
    site_dir = Path(os.path.normpath(Path(site_dir).resolve()))
    tr_tree = site_dir / TR_TREE
    bad = []
    for page in sorted(site_dir.rglob("*.html")):
        parser = _Links()
        parser.feed(page.read_text(encoding="utf-8", errors="replace"))
        where = page.relative_to(site_dir).as_posix()
        in_tr = tr_tree in page.parents
        for url, alternate in parser.links:
            target = _target(site_dir, page, url, site_path)
            if target is None:
                continue
            if not target.is_file():
                bad.append(f"{where}: missing target {url!r}")
            elif in_tr and not alternate and tr_tree not in target.parents:
                bad.append(f"{where}: leaves {TR_TREE}/ {url!r}")
    return bad


def _tiny_tree(root: Path) -> None:
    """An English page and its Turkish counterpart, linking each other and their resources."""
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "site.js").write_text("", encoding="utf-8")
    (root / "hazelnut").mkdir()
    (root / "hazelnut" / "index.html").write_text(
        '<link rel="alternate" hreflang="tr" href="https://x.org/crop-markets/tr/hazelnut/index.html"'
        ' data-href="../tr/hazelnut/index.html">'
        '<script src="../assets/site.js"></script><a href="../index.html#top">home</a>'
        '<a href="./">here</a><a href="#x">x</a><a href="mailto:a@b.c">m</a>'
        '<a href="https://example.org/missing.html">ext</a><a href="//cdn.example/x.js">cdn</a>'
        '<a href="/crop-markets/hazelnut/index.html?q=1">abs</a><img src="data:image/png;base64,AA">'
        '<script>var s = \'<a href="nowhere.html">\';</script>',
        encoding="utf-8")
    (root / "index.html").write_text('<a href="hazelnut/index.html">h</a>', encoding="utf-8")
    tr = root / TR_TREE
    (tr / "assets").mkdir(parents=True)
    (tr / "assets" / "site.js").write_text("", encoding="utf-8")
    (tr / "hazelnut").mkdir()
    (tr / "hazelnut" / "index.html").write_text(
        '<link rel="alternate" hreflang="en" href="https://x.org/crop-markets/hazelnut/index.html"'
        ' data-href="../../hazelnut/index.html">'
        '<script src="../assets/site.js"></script><a href="../index.html">ana sayfa</a>',
        encoding="utf-8")
    (tr / "index.html").write_text('<a href="hazelnut/">h</a>', encoding="utf-8")


def test_link_problems_on_a_tiny_two_language_site(tmp_path):
    _tiny_tree(tmp_path)
    assert link_problems(tmp_path) == []


def test_link_problems_finds_missing_targets_in_either_tree(tmp_path):
    _tiny_tree(tmp_path)
    (tmp_path / "methods.html").write_text(
        '<a href="hazelnut/gone.html#a">x</a><img src="assets/nope%20here.png">', encoding="utf-8")
    (tmp_path / TR_TREE / "methods.html").write_text(
        '<a href="hazelnut/yok.html">x</a><a href="/crop-markets/tr/kayip.html">y</a>',
        encoding="utf-8")
    assert link_problems(tmp_path) == [
        "methods.html: missing target 'hazelnut/gone.html#a'",
        "methods.html: missing target 'assets/nope%20here.png'",
        "tr/methods.html: missing target 'hazelnut/yok.html'",
        "tr/methods.html: missing target '/crop-markets/tr/kayip.html'",
    ]


def test_link_problems_finds_turkish_links_that_leave_the_turkish_tree(tmp_path):
    _tiny_tree(tmp_path)
    # Each target exists, but in the English tree: a Turkish page must stay inside tr/
    # (only its language switch, the hreflang alternates, leads to English).
    (tmp_path / TR_TREE / "methods.html").write_text(
        '<a href="../hazelnut/index.html">x</a><script src="../assets/site.js"></script>'
        '<a href="/crop-markets/index.html">y</a>', encoding="utf-8")
    assert link_problems(tmp_path) == [
        "tr/methods.html: leaves tr/ '../hazelnut/index.html'",
        "tr/methods.html: leaves tr/ '../assets/site.js'",
        "tr/methods.html: leaves tr/ '/crop-markets/index.html'",
    ]


def test_link_problems_checks_the_language_switch_targets(tmp_path):
    _tiny_tree(tmp_path)
    (tmp_path / TR_TREE / "hazelnut" / "index.html").write_text(
        '<link rel="alternate" hreflang="en" href="https://x.org/crop-markets/hazelnut/x.html"'
        ' data-href="../../hazelnut/x.html">', encoding="utf-8")
    assert link_problems(tmp_path) == [
        "tr/hazelnut/index.html: missing target '../../hazelnut/x.html'",
    ]


@pytest.mark.skipif(not (RENDERED / TR_TREE).is_dir(),
                    reason="site/_site/tr not rendered (run scripts/render_site.py)")
def test_rendered_links_resolve_in_both_trees():
    assert (RENDERED / TR_TREE / "index.html").is_file()
    bad = link_problems(RENDERED)
    assert not bad, f"{len(bad)} broken link(s):\n" + "\n".join(bad[:30])


def test_missing_methods_anchors_per_language_tree(tmp_path):
    (tmp_path / "methods.html").write_text('<section id="sarima"></section>', encoding="utf-8")
    tr = tmp_path / TR_TREE
    tr.mkdir()
    (tr / "methods.html").write_text('<section id="sarima-tr"></section>', encoding="utf-8")
    (tr / "a.html").write_text('<a href="methods.html#sarima-tr">ok</a>', encoding="utf-8")
    # The English check reads only the English tree; the Turkish one its own methods page.
    assert missing_methods_anchors(tmp_path, skip=tr) == []
    assert missing_methods_anchors(tr) == []
    (tr / "b.html").write_text('<a href="methods.html#sarima">en id</a>', encoding="utf-8")
    assert missing_methods_anchors(tr) == ["b.html: #sarima"]

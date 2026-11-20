"""Rendered site: no root-absolute links outside the project subpath.

The site is a GitHub Pages project site served under /<repo>/ (the path of SITE_URL), so a
link like href="/assets/x.css" would point outside it and break. Links under the project
subpath are fine: Quarto writes 404.html that way on purpose, because Pages serves the 404
page at whatever URL was missing. Protocol-relative links ("//host/...") are not root paths.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

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


def missing_methods_anchors(site_dir: Path) -> list[str]:
    """Every `methods.html#id` link in the HTML under `site_dir` whose id is not in methods.html."""
    ids = set(ID_ATTR.findall((Path(site_dir) / "methods.html").read_text(encoding="utf-8")))
    bad = []
    for path in sorted(Path(site_dir).rglob("*.html")):
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
    bad = missing_methods_anchors(RENDERED)
    assert not bad, "methods.html anchors that do not exist:\n" + "\n".join(bad[:20])

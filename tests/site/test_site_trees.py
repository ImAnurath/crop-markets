"""Rendered site: an English tree in site/_site and a Turkish one in site/_site/tr that
pair up page for page (scripts/render_site.py renders both), link each other with
hreflang, and leave the 404 page and robots.txt to the root."""

import html
import json
import re
from pathlib import Path

import pytest
import yaml

from hazelnut.site.config import SITE_DIR

RENDERED = SITE_DIR / "_site"
TR = "tr"
ROOT_ONLY = ("404.html",)  # GitHub Pages serves only the root 404 page, so it is bilingual
HTML_LANG = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']([^"']+)["']""", re.I)
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
TAG_ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def _files(root: Path, pattern: str, skip: Path | None = None) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob(pattern)
            if p.is_file() and (skip is None or skip not in p.parents)}


def unpaired_pages(site_dir: Path) -> list[str]:
    """Pages present in only one language tree, as "en only: x" / "tr only: x"."""
    site_dir = Path(site_dir)
    en = _files(site_dir, "*.html", skip=site_dir / TR) - set(ROOT_ONLY)
    tr = _files(site_dir / TR, "*.html")
    return ([f"en only: {p}" for p in sorted(en - tr)]
            + [f"tr only: {p}" for p in sorted(tr - en)])


def wrong_lang_pages(site_dir: Path) -> list[str]:
    """Pages whose <html lang> is not their tree's language."""
    site_dir = Path(site_dir)
    bad = []
    for lang, root, skip in (("en", site_dir, site_dir / TR), (TR, site_dir / TR, None)):
        for rel in sorted(_files(root, "*.html", skip)):
            m = HTML_LANG.search((root / rel).read_text(encoding="utf-8", errors="replace"))
            found = m.group(1) if m else None
            if found != lang:
                bad.append(f"{(root / rel).relative_to(site_dir).as_posix()}: lang={found!r}")
    return bad


def site_roots() -> dict[str, str]:
    """Each language's site root from its profile's website.site-url, default (en) first."""
    def site_url(name):
        cfg = yaml.safe_load((SITE_DIR / name).read_text(encoding="utf-8"))
        return (cfg.get("website") or {}).get("site-url")
    return {"en": site_url("_quarto.yml"), TR: site_url(f"_quarto-{TR}.yml")}


def alternates(page_html: str) -> dict[str, tuple[str, str]]:
    """The page's <link rel="alternate" hreflang> links: {hreflang: (href, data-href)}."""
    out = {}
    for tag in LINK_TAG.findall(page_html):
        attrs = {m[0].lower(): html.unescape(m[1] or m[2]) for m in TAG_ATTR.findall(tag)}
        if attrs.get("rel") == "alternate" and "hreflang" in attrs:
            out[attrs["hreflang"]] = (attrs.get("href"), attrs.get("data-href"))
    return out


def hreflang_problems(site_dir: Path, roots: dict[str, str]) -> list[str]:
    """Pages (all but the root-only ones) whose hreflang links are missing or lead nowhere.
    Each page links every language and x-default (= the first language): `href` is that
    language's root plus the page path; `data-href`, relative to the page, reaches the
    same rendered file."""
    site_dir = Path(site_dir)
    default = next(iter(roots))
    trees = {lang: site_dir / url[len(roots[default]):] for lang, url in roots.items()}
    bad = []
    for lang, tree in trees.items():
        skip = trees[TR] if lang == default else None
        for rel in sorted(_files(tree, "*.html", skip) - set(ROOT_ONLY)):
            page = tree / rel
            where = page.relative_to(site_dir).as_posix()
            links = alternates(page.read_text(encoding="utf-8", errors="replace"))
            if set(links) != {*roots, "x-default"}:
                bad.append(f"{where}: hreflang {sorted(links)}")
                continue
            for target, (href, data_href) in links.items():
                to = default if target == "x-default" else target
                if href != roots[to] + rel:
                    bad.append(f"{where}: {target} href {href!r}")
                if not data_href or (page.parent / data_href).resolve() != (trees[to] / rel).resolve():
                    bad.append(f"{where}: {target} data-href {data_href!r}")
                elif not (trees[to] / rel).is_file():
                    bad.append(f"{where}: {target} target missing")
    return bad


def _page(path: Path, lang: str, head: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<!DOCTYPE html>\n<html xmlns="x" lang="{lang}" xml:lang="{lang}">'
                    f"<head>{head}</head>", "utf-8")


def _links(rel: str, en_href: str, tr_href: str) -> str:
    return "".join(
        f'<link rel="alternate" hreflang="{h}" href="https://x.org/cm/{p}{rel}" data-href="{d}">'
        for h, p, d in (("en", "", en_href), ("tr", "tr/", tr_href), ("x-default", "", en_href)))


def test_page_pairing_on_a_tiny_site(tmp_path):
    for rel in ("index.html", "hazelnut/index.html", "hazelnut/analyses/a.html"):
        _page(tmp_path / rel, "en")
        _page(tmp_path / TR / rel, "tr")
    assert unpaired_pages(tmp_path) == []
    assert wrong_lang_pages(tmp_path) == []
    _page(tmp_path / "404.html", "en")  # root only
    assert unpaired_pages(tmp_path) == []

    _page(tmp_path / "methods.html", "en")
    _page(tmp_path / TR / "hazelnut" / "extra.html", "en")
    assert unpaired_pages(tmp_path) == ["en only: methods.html", "tr only: hazelnut/extra.html"]
    assert wrong_lang_pages(tmp_path) == ["tr/hazelnut/extra.html: lang='en'"]


def test_hreflang_check_on_a_tiny_site(tmp_path):
    roots = {"en": "https://x.org/cm/", TR: "https://x.org/cm/tr/"}
    _page(tmp_path / "index.html", "en", _links("index.html", "index.html", "tr/index.html"))
    _page(tmp_path / TR / "index.html", TR, _links("index.html", "../index.html", "index.html"))
    _page(tmp_path / "a" / "b.html", "en", _links("a/b.html", "b.html", "../tr/a/b.html"))
    _page(tmp_path / TR / "a" / "b.html", TR, _links("a/b.html", "../../a/b.html", "b.html"))
    _page(tmp_path / "404.html", "en")
    assert hreflang_problems(tmp_path, roots) == []

    _page(tmp_path / TR / "a" / "b.html", TR, _links("a/b.html", "../a/b.html", "b.html"))
    _page(tmp_path / "c.html", "en")
    assert hreflang_problems(tmp_path, roots) == [
        "c.html: hreflang []",
        "tr/a/b.html: en data-href '../a/b.html'",
        "tr/a/b.html: x-default data-href '../a/b.html'",
    ]


def test_site_langs_match_the_profiles_site_urls():
    # filters/lang-links.lua builds the hreflang hrefs from site-langs; the profiles'
    # site-url drive the sitemaps and the 404 page's links.
    cfg = yaml.safe_load((SITE_DIR / "_quarto.yml").read_text(encoding="utf-8"))
    assert {e["lang"]: e["url"] for e in cfg["site-langs"]} == site_roots()
    assert cfg["site-langs"][0]["lang"] == "en"  # x-default


needs_both_trees = pytest.mark.skipif(
    not (RENDERED / TR).is_dir(),
    reason="site/_site/tr not rendered (run scripts/render_site.py)")


@needs_both_trees
def test_rendered_trees_pair_up_page_for_page():
    assert (RENDERED / "hazelnut" / "index.html").is_file()
    bad = unpaired_pages(RENDERED)
    assert not bad, "pages without a counterpart:\n" + "\n".join(bad[:20])


@needs_both_trees
def test_rendered_pages_carry_their_tree_language():
    bad = wrong_lang_pages(RENDERED)
    assert not bad, "pages with the wrong <html lang>:\n" + "\n".join(bad[:20])


@needs_both_trees
def test_turkish_tree_has_its_own_copy_of_assets_and_data():
    # Turkish pages use the same relative paths (../assets/site.js, the explorer's
    # ../data/<crop>/*.csv), so each tree carries the resources.
    for folder in ("assets", "data"):
        en = _files(RENDERED / folder, "*")
        assert en, f"_site/{folder} is empty"
        assert _files(RENDERED / TR / folder, "*") == en, f"_site/tr/{folder} differs from _site/{folder}"
    assert not (RENDERED / TR / "_site").exists(), "the Turkish render copied the English tree"


@needs_both_trees
def test_rendered_pages_link_their_counterparts_with_hreflang():
    bad = hreflang_problems(RENDERED, site_roots())
    assert not bad, "pages with wrong hreflang links:\n" + "\n".join(bad[:20])


def _strings(page: Path) -> dict:
    m = re.search(r'<script type="application/json" id="site-strings">(.*?)</script>',
                  page.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)) if m else {}


@needs_both_trees
def test_rendered_pages_carry_their_language_strings_for_site_js():
    for rel in ("index.html", "hazelnut/analyses/exports.html"):
        en, tr = _strings(RENDERED / rel), _strings(RENDERED / TR / rel)
        for key in ("theme-toggle", "chart-failed"):
            assert en[key] and tr[key] and en[key] != tr[key], key
        for s in (en, tr):
            langs = s["lang-switch"]["langs"]
            assert [x["lang"] for x in langs] == [TR, "en"]
            assert all(x["code"] and x["title"] for x in langs)
    assert _strings(RENDERED / "404.html")["lang-switch"]


def _title(page_html: str) -> str:
    return html.unescape(re.search(r"<title>(.*?)</title>", page_html, re.S).group(1)).strip()


def _h1s(page_html: str) -> list[str]:
    """The page's own <h1>s (not Quarto's hidden title-block one), as plain text."""
    found = re.findall(r'<h1\b(?![^>]*class="title")[^>]*>(.*?)</h1>', page_html, re.S)
    return [" ".join(html.unescape(re.sub(r"<[^>]+>", "", h)).split()) for h in found]


@needs_both_trees
def test_turkish_tree_is_in_turkish():
    qmd = (SITE_DIR / "hazelnut" / "index.qmd").read_text(encoding="utf-8")
    meta = yaml.safe_load(qmd.split("---")[1])
    en = (RENDERED / "hazelnut" / "index.html").read_text(encoding="utf-8")
    tr = (RENDERED / TR / "hazelnut" / "index.html").read_text(encoding="utf-8")
    assert _title(en).startswith(meta["title"])
    assert _title(tr).startswith(meta["title-tr"]) and meta["title"] not in _title(tr)
    en_h1, tr_h1 = _h1s(en), _h1s(tr)
    assert en_h1 and tr_h1 and not set(en_h1) & set(tr_h1)
    assert en_h1[0] not in html.unescape(tr) and tr_h1[0] not in html.unescape(en)


@needs_both_trees
def test_only_the_root_serves_the_404_page_and_robots_txt():
    roots = site_roots()
    assert not (RENDERED / TR / "404.html").exists()
    assert not (RENDERED / TR / "robots.txt").exists()
    assert (RENDERED / TR / "sitemap.xml").is_file()
    robots = (RENDERED / "robots.txt").read_text(encoding="utf-8").splitlines()
    assert [x for x in robots if x.startswith("Sitemap:")] == [
        f"Sitemap: {roots['en']}sitemap.xml", f"Sitemap: {roots[TR]}sitemap.xml"]
    # The root 404 page holds both languages, each with a button to its own tree's home
    # (the page's script finds the trees from them).
    page = (RENDERED / "404.html").read_text(encoding="utf-8")
    for lang, home in (("en", "/crop-markets/index.html"), (TR, f"/crop-markets/{TR}/index.html")):
        block = re.search(rf'<div\b[^>]*\blang="{lang}"[^>]*>(.*?)</div>\s*</div>', page, re.S)
        assert block and "<h1" in block.group(1), f"404 page has no {lang} block"
        hrefs = [h.replace("/./", "/") for h in re.findall(r'href="([^"]+)"', block.group(1))]
        assert home in hrefs, f"404 {lang} block does not link {home}: {hrefs}"


CHART_JSON = re.compile(r'<div class="chart[^"]*"[^>]*\bdata-plotly\b[^>]*>'
                        r'<script type="application/json">(.*?)</script></div>', re.S)


def _chart_specs(page: Path) -> list[dict]:
    return [json.loads(s) for s in CHART_JSON.findall(page.read_text(encoding="utf-8"))]


@needs_both_trees
def test_rendered_turkish_charts_are_turkish_and_english_ones_carry_no_locale():
    from tests.site.test_charts import _english_chart_words, _visible_strings, _words

    english = _english_chart_words()
    found = 0
    for rel in sorted(_files(RENDERED / TR, "*.html")):
        en, tr = _chart_specs(RENDERED / rel), _chart_specs(RENDERED / TR / rel)
        assert len(en) == len(tr), rel
        for spec in en:
            assert "separators" not in spec["layout"] and "locale" not in spec["config"], rel
        for spec in tr:
            found += 1
            assert spec["layout"]["separators"] == ",." and spec["config"]["locale"] == "tr", rel
            words = set().union(*map(_words, _visible_strings(spec)))
            assert not words & english, (rel, sorted(words & english))
    assert found >= 14  # dashboard 4, analyses 10

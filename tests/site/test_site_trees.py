"""Rendered site: an English tree in site/_site and a Turkish one in site/_site/tr that
pair up page for page (scripts/render_site.py renders both)."""

import re
from pathlib import Path

import pytest

from hazelnut.site.config import SITE_DIR

RENDERED = SITE_DIR / "_site"
TR = "tr"
HTML_LANG = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']([^"']+)["']""", re.I)


def _files(root: Path, pattern: str, skip: Path | None = None) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob(pattern)
            if p.is_file() and (skip is None or skip not in p.parents)}


def unpaired_pages(site_dir: Path) -> list[str]:
    """Pages present in only one language tree, as "en only: x" / "tr only: x"."""
    site_dir = Path(site_dir)
    en = _files(site_dir, "*.html", skip=site_dir / TR)
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


def _page(path: Path, lang: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<!DOCTYPE html>\n<html xmlns="x" lang="{lang}" xml:lang="{lang}">', "utf-8")


def test_page_pairing_on_a_tiny_site(tmp_path):
    for rel in ("index.html", "hazelnut/index.html", "hazelnut/analyses/a.html"):
        _page(tmp_path / rel, "en")
        _page(tmp_path / TR / rel, "tr")
    assert unpaired_pages(tmp_path) == []
    assert wrong_lang_pages(tmp_path) == []

    _page(tmp_path / "methods.html", "en")
    _page(tmp_path / TR / "hazelnut" / "extra.html", "en")
    assert unpaired_pages(tmp_path) == ["en only: methods.html", "tr only: hazelnut/extra.html"]
    assert wrong_lang_pages(tmp_path) == ["tr/hazelnut/extra.html: lang='en'"]


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

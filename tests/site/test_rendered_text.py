"""English must not change by accident: the visible text of every rendered English page
equals its snapshot in tests/site/fixtures/en_text/ (scripts/snapshot_text.py).

A deliberate English change updates the snapshot in the same commit:
    python scripts/snapshot_text.py site/_site
"""

import difflib
import importlib.util
from pathlib import Path

import pytest

from hazelnut.site.config import SITE_DIR

RENDERED = SITE_DIR / "_site"
FIXTURES = Path(__file__).parent / "fixtures" / "en_text"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "snapshot_text.py"


def _snapshot_module():
    spec = importlib.util.spec_from_file_location("snapshot_text", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


snapshot = _snapshot_module()


def test_page_text_keeps_visible_text_and_drops_scripts_and_svg():
    html = (
        "<html><head><title>T</title><style>p{}</style></head><body>"
        "<nav aria-label='Site'><a href='x'>Home</a></nav>"
        "<p>Price  <b>$4.13</b>\n /kg<svg><use href='#a'/><text>no</text></svg></p>"
        "<script>var no = 1;</script><img alt='A field'><div><span>a</span><span>b</span></div>"
        "<br/><p>x &amp; y</p></body></html>"
    )
    assert snapshot.page_text(html) == (
        "[aria-label] Site\nHome\nPrice $4.13 /kg\n[alt] A field\nab\nx & y\n"
    )


def test_snapshot_names_skip_the_turkish_tree(tmp_path):
    for rel in ("index.html", "hazelnut/analyses/a.html", "tr/index.html"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("<p>x</p>", encoding="utf-8")
    assert sorted(snapshot.site_texts(tmp_path)) == ["hazelnut__analyses__a.txt", "index.txt"]


def text_differences(site_dir: Path, fixtures: Path) -> list[str]:
    """Pages whose text differs from the snapshot (with a short diff), or that are new or
    missing."""
    rendered = snapshot.site_texts(site_dir)
    expected = {p.name: p.read_text(encoding="utf-8") for p in fixtures.glob("*.txt")}
    problems = [f"missing page: {n}" for n in sorted(set(expected) - set(rendered))]
    problems += [f"new page: {n}" for n in sorted(set(rendered) - set(expected))]
    for name in sorted(set(expected) & set(rendered)):
        if rendered[name] != expected[name]:
            diff = difflib.unified_diff(expected[name].splitlines(), rendered[name].splitlines(),
                                        "snapshot", "rendered", n=0, lineterm="")
            problems.append(f"{name}:\n" + "\n".join(list(diff)[2:12]))
    return problems


def test_fixtures_exist():
    assert len(list(FIXTURES.glob("*.txt"))) >= 13


@pytest.mark.skipif(not RENDERED.is_dir(), reason="site/_site not rendered (run scripts/render_site.py)")
def test_rendered_english_text_matches_the_snapshot():
    assert text_differences(RENDERED, FIXTURES) == []

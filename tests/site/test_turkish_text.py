"""No English left on the translated Turkish pages: the visible text of each page in
TRANSLATED (navbar and footer included), read with scripts/snapshot_text.py's extractor,
holds none of a compact list of common English words.

Pages join TRANSLATED as their Turkish prose lands (Task 6 batches). Names that stay as
they are in Turkish (sources, method names, the site's brand) are removed before the scan.

The stop-word list catches untranslated sentences. It does not catch short English
fragments made of words outside the list (a lone label such as "Calm"), and it never sees
chart text inside Plotly's JSON (scripts are dropped); tests/site/test_charts.py covers those.
"""

import importlib.util
import re
from pathlib import Path

import pytest

from hazelnut.site.config import SITE_DIR

RENDERED = SITE_DIR / "_site"
TR_TREE = RENDERED / "tr"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "snapshot_text.py"

# Turkish pages whose prose is translated, relative to the Turkish tree.
TRANSLATED = (
    "index.html",
    "hazelnut/index.html",
    "hazelnut/dashboard.html",
)
# Root-only bilingual pages (GitHub Pages serves only the root 404): their lang="tr"
# block is scanned. Their navbar and footer are the English tree's by design.
ROOT_TR_BLOCKS = ("404.html",)

# Common English words that are not also Turkish words ("on" is ten, "it" a dog, "not" a
# note, "has" pure, "at" a horse, "can" soul, "be" a letter name, so they are left out).
ENGLISH_WORDS = frozenset("""
    the and of to in is are was were with for from this that which these those or been
    by its into than then there their they we our you your what how where when why will
    would could only also more most all each every about after before over under
    price prices season seasons seasonal export exports exported crop crops market markets
    forecast forecasts forecasting month months year years week weekly data page range
    error errors method methods chart charts dashboard overview analyses analysis explorer
    downloads download source sources estimate shock shocks naive holdout share volume
    exchange skip main content toggle navigation refreshed average horizon scoreboard
""".split())

# Names kept as they are in Turkish (site/i18n/glossary.md): removed before the scan.
ALLOWED = (
    "Crop Markets",
    "UN Comtrade", "FAOSTAT", "TOBB", "Open-Meteo", "ECB", "OECD",
    "SARIMAX", "SARIMA", "Chronos-Bolt", "LightGBM", "FOB",
    "GitHub", "LinkedIn", "Wikimedia Commons", "CC BY-SA 4.0", "CC BY 4.0", "Excel",
    "USD", "TL", "$/kg", "kg",
)
# A word, but not a suffix after an apostrophe ("1'in", "Türkiye'de").
_WORD = re.compile(r"(?<![\w'’])[^\W\d_]+")


def _snapshot_module():
    spec = importlib.util.spec_from_file_location("snapshot_text", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


snapshot = _snapshot_module()


def english_words(text: str) -> list[str]:
    """The English words in ``text``, in order, after the allowed names are removed."""
    for name in ALLOWED:
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ", text)
    return [w for w in _WORD.findall(text) if w.casefold() in ENGLISH_WORDS]


def english_lines(text: str) -> list[str]:
    """Each line of ``text`` that holds English words, as "line  <- words"."""
    out = []
    for line in text.splitlines():
        found = english_words(line)
        if found:
            out.append(f"{line[:120]}  <- {', '.join(found)}")
    return out


def tr_block(html: str) -> str:
    """The lang="tr" block of a bilingual root page (up to its script)."""
    m = re.search(r'<div\b[^>]*\blang="tr".*?(?=<script|</main)', html, re.S)
    return m.group(0) if m else ""


def test_english_words_skips_turkish_and_allowed_names():
    assert english_words("Fiyat, USD · İhracat için UN Comtrade; Crop Markets") == []
    assert english_words("Türkiye'de the price, için") == ["the", "price"]
    assert english_words("SARIMA ile naif tahmin; Prices in TL") == ["Prices", "in"]
    assert english_words("1'in üzeri, Türkiye’de") == []


def test_tr_block_takes_only_the_turkish_block():
    html = ('<div lang="en"><p>Back to the start</p></div>'
            '<div lang="tr"><p>Ana sayfaya dönün</p></div><script>x</script>')
    assert snapshot.page_text(tr_block(html)) == "Ana sayfaya dönün\n"


@pytest.mark.skipif(not TR_TREE.is_dir(), reason="Turkish tree not rendered (run scripts/render_site.py)")
@pytest.mark.parametrize("page", TRANSLATED)
def test_translated_turkish_page_has_no_english(page):
    path = TR_TREE / page
    assert path.is_file(), f"missing Turkish page {page}"
    text = snapshot.page_text(path.read_text(encoding="utf-8"))
    assert english_lines(text) == []


@pytest.mark.skipif(not RENDERED.is_dir(), reason="site/_site not rendered (run scripts/render_site.py)")
@pytest.mark.parametrize("page", ROOT_TR_BLOCKS)
def test_turkish_block_of_root_page_has_no_english(page):
    block = tr_block((RENDERED / page).read_text(encoding="utf-8"))
    assert block, f"{page} has no lang=\"tr\" block"
    assert english_lines(snapshot.page_text(block)) == []

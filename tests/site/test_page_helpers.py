"""Formatting and markup helpers for the overview and home pages."""
import json

import pytest

from hazelnut.site import page_helpers as ph
from hazelnut.site.config import CropConfig, LocalCurrency

STATS = {
    "as_of": "2026-09",
    "usd_kg": 4.2824,
    "usd_mom": -0.05296446184126136,
    "try_kg": 208.15,
    "try_mom": -0.03729638228791843,
    "peak_usd": 7.5861,
    "peak_month": "2015-05",
    "from_peak": -0.43549386377717136,
    "crop_estimate_t": 86440.0,
    "crop_yoy": 0.31497680079105494,
    "crop_year": 2026,
}


def manifest(**stale_as_of):
    outputs = {
        "prices_monthly": {"as_of": "2026-09", "rows": 381, "stale": False},
        "exports_monthly": {"as_of": "2025-12", "rows": 10, "stale": False},
        "crop_by_year": {"as_of": "2026", "rows": 37, "stale": False},
    }
    for name, as_of in stale_as_of.items():
        outputs[name] = {"as_of": as_of, "rows": 1, "stale": True}
    return {"crop": "hazelnut", "built_at": "x", "as_of": "2026-09", "outputs": outputs}


# --- number formats -------------------------------------------------------------------

def test_usd_price_has_two_decimals():
    assert ph.fmt_usd(4.2824) == "$4.28"
    assert ph.fmt_usd(1234.5) == "$1,234.50"


def test_local_price_has_two_decimals_and_thousands():
    assert ph.fmt_number(208.15) == "208.15"
    assert ph.fmt_number(12345.6) == "12,345.60"


@pytest.mark.parametrize(
    "value, expected",
    [
        (-0.05296446184126136, "−5.3%"),
        (0.31497680079105494, "+31.5%"),
        (-0.43549386377717136, "−43.5%"),
        (0.0, "0.0%"),
        (-0.0004, "0.0%"),  # rounds to zero: no sign
    ],
)
def test_change_is_signed_percent_with_one_decimal(value, expected):
    assert ph.fmt_change(value) == expected


def test_tonnes_have_thousands_separators():
    assert ph.fmt_tonnes(86440.0) == "86,440"
    assert ph.fmt_tonnes(1234567.4) == "1,234,567"


@pytest.mark.parametrize("fn", [ph.fmt_usd, ph.fmt_number, ph.fmt_change, ph.fmt_tonnes])
def test_missing_values_show_n_a(fn):
    assert fn(None) == "n/a"
    assert fn(float("nan")) == "n/a"


# --- months -----------------------------------------------------------------------------

def test_month_label():
    assert ph.month_label("2026-09") == "September 2026"
    assert ph.month_label("2025-12") == "December 2025"
    assert ph.month_label("2026") == "2026"  # yearly outputs (crop, frost)


def test_previous_month_name_wraps_the_year():
    assert ph.previous_month_name("2026-09") == "August"
    assert ph.previous_month_name("2026-01") == "December"


# --- as-of stamp ------------------------------------------------------------------------

def test_stamp_without_stale_outputs():
    assert ph.as_of_stamp(manifest()) == "Data as of September 2026 · refreshed weekly"


def test_stamp_names_the_oldest_stale_source():
    m = manifest(ordu_monthly="2026-05", stats="2026-07")
    assert ph.as_of_stamp(m) == (
        "Data as of September 2026 · refreshed weekly (some sources from May 2026)"
    )


def test_stamp_compares_months_not_strings():
    # "2025-12" is older than "2026-02"; a yearly as_of is a year, not a month.
    m = manifest(a="2026-02", b="2025-12", c="2026")
    assert ph.as_of_stamp(m).endswith("(some sources from December 2025)")


def test_stamp_with_a_stale_yearly_output():
    assert ph.as_of_stamp(manifest(frost_by_year="2024")).endswith("(some sources from 2024)")


def _missing(m, name):
    """The entry write_site_data records for an output that failed with no earlier file."""
    m["outputs"][name] = {"as_of": None, "rows": 0, "stale": True}
    return m


def test_stamp_with_only_an_undated_stale_output():
    assert ph.as_of_stamp(_missing(manifest(), "exports_top")) == (
        "Data as of September 2026 · refreshed weekly (some sources unavailable)"
    )


def test_stamp_with_dated_and_undated_stale_outputs():
    m = _missing(manifest(ordu_monthly="2026-05"), "exports_top")
    assert ph.as_of_stamp(m).endswith("(some sources from May 2026, some unavailable)")


def test_meta_row_renders_with_an_undated_stale_output():
    assert "some sources unavailable" in ph.market_meta_html(_missing(manifest(), "frost_by_year"))


def test_output_month_label():
    m = _missing(manifest(), "exports_top")
    assert ph.output_month_label(m, "exports_monthly") == "December 2025"
    assert ph.output_month_label(m, "crop_by_year") == "2026"
    assert ph.output_month_label(m, "exports_top") is None  # failed, no earlier file
    assert ph.output_month_label(m, "not_built") is None
    assert ph.output_month_label(None, "exports_monthly") is None


# --- stat strip -------------------------------------------------------------------------

def strip(stats=STATS):
    return ph.market_strip_html(stats, local_name="lira", local=LocalCurrency("TL", "try_kg"), crop_source="Giresun")


def test_strip_shows_the_four_stats_from_stats_json():
    html = strip()
    assert html.count('class="stat"') == 4
    for text in [
        "Price, USD", "$4.28<small> /kg</small>",
        "Price, lira", "208.15<small> TL/kg</small>",
        "From the peak", "−43.5%", "since May 2015 ($7.59)",
        "Giresun crop estimate, 2026", "86,440<small> t</small>",
    ]:
        assert text in html, text
    assert html.count("on August") == 2
    assert '<span class="down">−5.3%</span> on August' in html
    assert '<span class="down">−3.7%</span> on August' in html
    assert "<span>+31.5%</span> on 2025" in html
    assert "Giresun," not in html  # the source is in the label, not the sub-line


def test_strip_label_names_the_crop_source_and_year():
    html = ph.market_strip_html(STATS, local_name="lira", local=LocalCurrency("TL", "try_kg"),
                                crop_source="Ordu")
    assert "Ordu crop estimate, 2026" in html and "Giresun" not in html


def test_strip_without_a_crop_estimate():
    stats = dict(STATS, crop_estimate_t=None, crop_yoy=None, crop_year=None)
    html = strip(stats)
    assert "Giresun crop estimate<" in html
    assert ">n/a<" in html
    assert "no estimate yet" in html
    assert "None" not in html and "nan" not in html


def test_strip_with_an_estimate_but_no_earlier_year():
    html = strip(dict(STATS, crop_yoy=None))
    assert "86,440" in html
    assert "no earlier year to compare" in html


def test_strip_with_missing_changes_and_peak():
    stats = dict(STATS, usd_mom=None, try_mom=None, from_peak=None, peak_usd=None, peak_month=None)
    html = strip(stats)
    assert "None" not in html
    assert html.count("<span>n/a</span> on August") == 2
    assert "class=\"down\"" not in html.split("From the peak")[0]


def test_strip_escapes_text():
    html = ph.market_strip_html(STATS, local_name="<b>", local=LocalCurrency("T&L", "try_kg"), crop_source="G<x>")
    assert "<b>" not in html and "G<x>" not in html
    assert "T&amp;L/kg" in html


def test_strip_reads_files(tmp_path):
    (tmp_path / "stats.json").write_text(json.dumps(STATS), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest()), encoding="utf-8")
    stats, man = ph.load_page_data(tmp_path)
    assert stats["usd_kg"] == STATS["usd_kg"]
    assert man["as_of"] == "2026-09"


# --- home page crop list --------------------------------------------------------------

def crop(slug="hazelnut", name="Hazelnut", country="Turkey", exchanges=("Giresun", "Ordu")):
    return CropConfig(
        slug=slug, name=name, country=country, exchanges=tuple(exchanges),
        sections=("overview",), analyses=(), range_currencies=("usd",),
        local_currency=LocalCurrency("TL", "try_kg"),
    )


def test_exchanges_phrase():
    assert ph.exchanges_phrase(("Giresun", "Ordu")) == "Giresun & Ordu exchanges"
    assert ph.exchanges_phrase(("Giresun",)) == "Giresun exchange"
    assert ph.exchanges_phrase(("A", "B", "C")) == "A, B & C exchanges"


def test_crop_cards_link_each_crop_relatively(tmp_path):
    (tmp_path / "hazelnut").mkdir()
    (tmp_path / "hazelnut" / "stats.json").write_text(json.dumps(STATS), encoding="utf-8")
    crops = {"hazelnut": crop(), "figs": crop("figs", "Dried figs", "Greece", ("Aydin",))}
    html = ph.crop_cards_html(crops, data_dir=tmp_path)
    assert 'href="hazelnut/index.qmd"' in html
    assert 'href="figs/index.qmd"' in html
    assert 'href="/' not in html
    assert "Hazelnut" in html and "Turkey" in html and "Giresun &amp; Ordu exchanges" in html
    assert "$4.28/kg in September 2026" in html
    # A crop without built data still gets a card, just no price line.
    figs = html.split('href="figs/index.qmd"')[1]
    assert "Dried figs" in figs and "Greece" in figs and "/kg" not in figs


def test_meta_row_carries_the_label_and_stamp():
    html = ph.market_meta_html(manifest(stats="2026-07"))
    assert '<span class="eyebrow">The market this month</span>' in html
    assert "Data as of September 2026 · refreshed weekly (some sources from July 2026)" in html
    assert '<i aria-hidden="true"></i>' in html


# --- sources byline ---------------------------------------------------------------------

def _listed_providers(text):
    """Count the providers named in the visible list ("A & B exchanges" names two)."""
    n = 0
    for item in text.split(", "):
        n += len(item.removesuffix(" exchanges").removesuffix(" exchange").split(" & "))
    return n


def test_sources_summary_counts_and_names_every_provider():
    from hazelnut.site.crops import crop_module

    sources = crop_module("hazelnut").WORKBOOK_SOURCES
    count, text = ph.sources_summary(sources)
    assert count == f"{len(sources)} public datasets"
    assert _listed_providers(text) == len(sources)
    assert text == "Giresun & Ordu exchanges, UN Comtrade, FAOSTAT, TOBB, Open-Meteo, ECB, OECD"


def test_sources_summary_singular_and_no_exchanges():
    count, text = ph.sources_summary([("FAOSTAT", "x", "u", "l")])
    assert (count, text) == ("1 public dataset", "FAOSTAT")


# --- Methods: holdout glossary --------------------------------------------------------

def test_holdout_glossary_names_the_period():
    assert ph.holdout_glossary_sentence([("Hazelnut", ("2024-10", "2026-09"))]) == (
        "For hazelnut the holdout is October 2024 to September 2026 (24 months). "
        "It was set aside before any method was built."
    )


def test_holdout_glossary_with_two_crops_and_none():
    two = ph.holdout_glossary_sentence([("Hazelnut", ("2024-10", "2026-09")), ("Fig", ("2025-01", "2025-12"))])
    assert two == ("For hazelnut the holdout is October 2024 to September 2026 (24 months); for fig, "
                   "January 2025 to December 2025 (12 months). Each was set aside before any method was built.")
    assert ph.holdout_glossary_sentence([]) == (
        "The final months of the backtest were set aside before any method was built."
    )


# --- Turkish ----------------------------------------------------------------------------

def test_strip_and_meta_row_in_turkish(turkish):
    html = ph.market_meta_html(manifest()) + strip()
    for text in [
        "Bu ayki piyasa", "Veriler Eylül 2026 itibarıyla",
        "Fiyat, USD", "4,28 $<small> /kg</small>", "208,15<small> TL/kg</small>",
        "Zirveden bu yana", "−%43,5", "zirve: Mayıs 2015 (7,59 $)",
        "Giresun rekolte tahmini, 2026", "86.440<small> t</small>",
        'Ağustos ayına göre <span class="down">−%5,3</span>',
        "2025 yılına göre <span>+%31,5</span>",
    ]:
        assert text in html, text
    assert "on August" not in html and "Price" not in html


def test_sources_summary_and_exchanges_in_turkish(turkish):
    import importlib

    from hazelnut.site import hazelnut_data

    # The crop module reads its words when it is imported; reload it in Turkish.
    sources = importlib.reload(hazelnut_data).WORKBOOK_SOURCES
    try:
        count, text = ph.sources_summary(sources)
        assert count == f"{len(sources)} kamuya açık veri seti"
        assert text.startswith("Giresun ve Ordu borsaları, UN Comtrade, FAOSTAT")
    finally:
        import hazelnut.site.i18n as i18n

        i18n.LANG = "en"
        importlib.reload(hazelnut_data)


def test_holdout_glossary_in_turkish_lowers_the_crop_name(turkish):
    two = ph.holdout_glossary_sentence([("Fındık", ("2024-10", "2026-09")),
                                        ("İncir", ("2025-01", "2025-12"))])
    assert two == ("Ayrılmış test dönemi fındık için Ekim 2024 – Eylül 2026 (24 ay); incir için "
                   "Ocak 2025 – Aralık 2025 (12 ay). Her biri, hiçbir yöntem kurulmadan önce "
                   "ayrıldı.")


# --- Methods: the facts panel's foot line (T6b3-m1) -------------------------------------

def test_facts_foot_html_escapes_the_sentence_but_not_the_link(monkeypatch):
    link = '<a href="hazelnut/analyses/forecasting.qmd">Hazelnut forecasting analysis</a>'
    assert ph.facts_foot_html(link) == (
        f'<p class="foot">{link}: every table behind these lines.</p>')
    # A sentence with markup characters is escaped; the link is put in as it is.
    monkeypatch.setattr(ph, "t", lambda key, **kw: "Tables & <notes> for {link}")
    assert ph.facts_foot_html(link) == f'<p class="foot">Tables &amp; &lt;notes&gt; for {link}</p>'

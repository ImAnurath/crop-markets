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


# --- stat strip -------------------------------------------------------------------------

def strip(stats=STATS):
    return ph.market_strip_html(stats, local_name="lira", local_unit="TL", crop_source="Giresun")


def test_strip_shows_the_four_stats_from_stats_json():
    html = strip()
    assert html.count('class="stat"') == 4
    for text in [
        "Price, USD", "$4.28<small> /kg</small>",
        "Price, lira", "208.15<small> TL/kg</small>",
        "From the peak", "−43.5%", "since May 2015 ($7.59)",
        "2026 crop estimate", "86,440<small> t</small>",
    ]:
        assert text in html, text
    assert html.count("on August") == 2
    assert '<span class="down">−5.3%</span> on August' in html
    assert '<span class="down">−3.7%</span> on August' in html
    assert "Giresun, <span>+31.5%</span> on 2025" in html


def test_strip_without_a_crop_estimate():
    stats = dict(STATS, crop_estimate_t=None, crop_yoy=None, crop_year=None)
    html = strip(stats)
    assert "Crop estimate" in html
    assert ">n/a<" in html
    assert "Giresun, no estimate yet" in html
    assert "None" not in html and "nan" not in html


def test_strip_with_an_estimate_but_no_earlier_year():
    html = strip(dict(STATS, crop_yoy=None))
    assert "86,440" in html
    assert "Giresun, no earlier year to compare" in html


def test_strip_with_missing_changes_and_peak():
    stats = dict(STATS, usd_mom=None, try_mom=None, from_peak=None, peak_usd=None, peak_month=None)
    html = strip(stats)
    assert "None" not in html
    assert html.count("<span>n/a</span> on August") == 2
    assert "class=\"down\"" not in html.split("From the peak")[0]


def test_strip_escapes_text():
    html = ph.market_strip_html(STATS, local_name="<b>", local_unit="T&L", crop_source="G<x>")
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

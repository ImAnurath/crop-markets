"""Helpers for the data explorer, Downloads and Methods pages (page_helpers, workbook,
the crop module) and the facts the Methods page computes from the site data."""
import json

import pandas as pd
import pytest
from openpyxl import load_workbook

from hazelnut.site import hazelnut_data
from hazelnut.site import page_helpers as ph
from hazelnut.site import validate
from hazelnut.site import workbook as wbmod
from hazelnut.site.config import SITE_DIR, CropConfig, LocalCurrency, load_crops

CROP = CropConfig("rye", "Rye", "Elsewhere", ("North", "South"), (), (), ("usd",),
                  LocalCurrency("ZZ", "zz_kg"))
SHEETS = {
    "Prices": ("prices_monthly.csv", {
        "month": ("Month", None), "season": ("Season", None), "usd_kg": ("USD/kg", "0.00"),
        "zz_kg": ("ZZ/kg", "0.00"), "usd_zz": ("ZZ per USD", "0.0000")}),
    "South": ("south_monthly.csv", {
        "month": ("Month", None), "season": ("Season", None), "zz_kg": ("ZZ/kg", "0.00"),
        "usd_kg": ("USD/kg", "0.00"), "trade_days": ("Trading days", "0")}),
    "Crop": ("crop_by_year.csv", {"year": ("Year", "0")}),
}
SOURCES = [
    ("North Commodity Exchange", "Monthly prices", "https://north.example/", "Credit the source"),
    ("Somebody", "Weather", "https://w.example/", "CC BY 4.0"),
]


# --- number formats -----------------------------------------------------------------------

@pytest.mark.parametrize("fmt, dp", [(None, None), ("0", 0), ("0.00", 2), ("0.0000", 4),
                                     ("#,##0", 0), ("#,##0.0", 1)])
def test_number_decimals_reads_the_workbook_format(fmt, dp):
    assert ph.number_decimals(fmt) == dp


# --- explorer -----------------------------------------------------------------------------

def _cfg():
    return ph.explorer_config(CROP, SHEETS, {"North": "Prices", "South": "South"}, SOURCES,
                              "../data/rye")


def test_explorer_config_takes_everything_from_the_crop_and_the_workbook_spec():
    cfg = _cfg()
    assert cfg["slug"] == "rye" and cfg["name"] == "Rye"
    assert cfg["currencies"] == [{"label": "USD", "column": "usd_kg"},
                                 {"label": "ZZ", "column": "zz_kg"}]
    assert [e["name"] for e in cfg["exchanges"]] == ["North", "South"]
    north, south = cfg["exchanges"]
    assert north["file"] == "../data/rye/prices_monthly.csv"
    assert south["file"] == "../data/rye/south_monthly.csv"
    assert north["columns"][0] == {"key": "month", "label": "Month", "decimals": None}
    assert {"key": "usd_zz", "label": "ZZ per USD", "decimals": 4} in north["columns"]
    # extras: every column but the month and the currency columns, in spec order
    assert north["extras"] == ["season", "usd_zz"]
    assert south["extras"] == ["season", "trade_days"]


def test_explorer_config_credits_the_exchange_from_the_sources_list():
    north, south = _cfg()["exchanges"]
    assert north["source"] == "North Commodity Exchange"
    assert north["terms"] == "Credit the source"
    assert south["source"] is None and south["terms"] is None  # no row starts with "South"


def test_explorer_config_skips_an_exchange_without_a_monthly_sheet():
    cfg = ph.explorer_config(CROP, SHEETS, {"North": "Prices"}, SOURCES, "d")
    assert [e["name"] for e in cfg["exchanges"]] == ["North"]


def test_explorer_config_is_json_ready():
    json.dumps(_cfg())


def test_hazelnut_explorer_sheets_cover_every_exchange():
    crop = load_crops()["hazelnut"]
    assert set(hazelnut_data.EXPLORER_SHEETS) == set(crop.exchanges)
    assert set(hazelnut_data.EXPLORER_SHEETS.values()) <= set(hazelnut_data.WORKBOOK_SHEETS)


# The explorer's interface text: every string the OJS cells show reaches them through
# ojs_define (cfg["ui"]), in the page's language.
EN_UI = {
    "exchange": "Exchange", "currency": "Currency", "columns": "Columns", "season": "Season",
    "latest": "Latest", "all": "All", "none": "None", "seasons_aria": "Seasons, newest first",
    "records": "Monthly records", "heading": "{exchange}, {seasons}",
    "rows": {"one": "{n} row", "other": "{n} rows"},
    "download": "Download this view (.xlsx)",
    "nothing": "Nothing to download: no months match these filters",
    "preparing": "Preparing the file…",
    "load_error": "The Excel library could not load. Check your connection and try again.",
    "make_error": "The file could not be made. Please try again.",
    "seasons_none": "no season selected", "seasons_one": "season {season}",
    "seasons_all": "all seasons", "seasons_run": "seasons {first} to {last}",
    "seasons_some": "{n} seasons",
    "table_aria": "Monthly records table",
    "table_caption": "Monthly records; select a column heading to sort",
    "unavailable": "These records could not be loaded. Reload the page to try again.",
    "empty": "No months match these filters.",
    "about": {
        "records_sheet": "Records", "sheet": "About", "title": "{crop} monthly records",
        "exchange": "Exchange", "currency": "Currency", "seasons": "Seasons", "rows": "Rows",
        "as_of": "Data as of", "source": "Source", "terms": "Credit and terms",
        "all_sources": "All sources and terms", "unknown": "unknown",
        "see_downloads": "See the Downloads page",
    },
}
# Turkish values that may equal the English ones (no words to translate).
SAME_IN_TR = {"heading"}


def _leaves(node, path=()):
    """(dotted path, text) for every string in a nested dict/list."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, (*path, str(k)))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, (*path, str(i)))
    elif isinstance(node, str):
        yield ".".join(path), node


def _english(text: str) -> list[str]:
    """English words in ``text`` (the rendered pages' stop-word check), {fields} aside."""
    import re

    from tests.site.test_turkish_text import english_words

    return english_words(re.sub(r"\{\w+\}", " ", text))


def test_explorer_ui_in_english_is_the_explorer_s_old_text():
    assert ph.explorer_ui() == EN_UI
    cfg = _cfg()
    assert cfg["ui"] == EN_UI and cfg["locale"] == "en-US"
    assert cfg["months"] == ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                             "Oct", "Nov", "Dec"]
    assert cfg["downloads_url"] == "https://imanurath.github.io/crop-markets/downloads.html"


def test_explorer_ui_in_turkish_translates_every_string(turkish):
    tr = dict(_leaves(ph.explorer_ui()))
    en = dict(_leaves(EN_UI))
    assert set(tr) == set(en)
    same = sorted(k for k in en if tr[k] == en[k] and k not in SAME_IN_TR)
    assert same == [], f"not translated: {same}"
    leftovers = {k: _english(v) for k, v in tr.items() if _english(v)}
    assert leftovers == {}
    for key in ("about.sheet", "about.records_sheet"):  # Excel's rules for a sheet name
        assert len(tr[key]) <= 31 and not set(tr[key]) & set("[]:*?/\\"), key


def test_explorer_config_in_turkish_has_no_english_leftovers(turkish):
    """The whole Turkish ojs_define config (interface text, column labels, credits) for the
    hazelnut explorer, through the same stop-word check as the rendered pages."""
    import importlib

    from hazelnut.site import i18n

    mod = importlib.reload(hazelnut_data)  # the crop module reads its words on import
    try:
        cfg = ph.explorer_config(load_crops()["hazelnut"], mod.WORKBOOK_SHEETS,
                                 mod.EXPLORER_SHEETS, mod.WORKBOOK_SOURCES, "../data/hazelnut")
    finally:
        i18n.LANG = "en"
        importlib.reload(hazelnut_data)
    assert cfg["locale"] == "tr-TR"
    assert cfg["months"][9] == "Eki"
    assert cfg["downloads_url"] == "https://imanurath.github.io/crop-markets/tr/downloads.html"
    skip = {"file", "slug", "key", "column", "downloads_url", "extras"}  # paths and ids
    texts = {k: v for k, v in _leaves(cfg) if not skip & set(k.split("."))}
    assert "exchanges.0.columns.0.label" in texts  # the column labels are scanned too
    leftovers = {k: _english(v) for k, v in texts.items() if _english(v)}
    assert leftovers == {}
    assert cfg["exchanges"][0]["columns"][0]["label"] == "Ay"
    assert cfg["exchanges"][0]["source"] == "Giresun Ticaret Borsası"


def _prices(months, values, col="zz_kg"):
    return pd.DataFrame({"month": months, col: values})


def test_explorer_outlier_note_names_the_far_months_and_links_the_analysis():
    months = ["2007-05", "2007-06", "2007-07", "2024-01"]
    ref = _prices(months, [4.0, 4.05, 4.1, 105.0])
    other = _prices(months, [3.6, 23.6, 3.7, 1300.0])
    html = ph.explorer_outlier_note(ref, other, "zz_kg", "South", "North",
                                    "analyses/exchanges.html")
    assert "June 2007 and January 2024" in html
    assert "more than 50%" in html and "North" in html and "South" in html
    assert "shown as published" in html
    assert 'href="analyses/exchanges.html"' in html


def test_explorer_outlier_note_is_none_without_far_months_or_without_a_link():
    m = ["2007-05", "2007-06"]
    assert ph.explorer_outlier_note(_prices(m, [4.0, 4.0]), _prices(m, [3.6, 3.7]),
                                    "zz_kg", "South", "North", "x.html") is None
    html = ph.explorer_outlier_note(_prices(m, [4.0, 4.0]), _prices(m, [3.6, 30.0]),
                                    "zz_kg", "South", "North", None)
    assert "June 2007" in html and "<a" not in html


def test_outlier_limit_is_shared():
    assert ph.OUTLIER_LIMIT == 0.5


# --- downloads ----------------------------------------------------------------------------

def test_workbook_filename_comes_from_the_slug():
    assert wbmod.workbook_filename("rye") == "rye-market-data.xlsx"


def test_sheet_list_matches_the_built_workbook(tiny_tables, tmp_path):
    from datetime import datetime, timezone

    from hazelnut.site.site_data import write_site_data

    crop = CropConfig("hazelnut", "Hazelnut", "Turkey", (), (), (), ("usd",),
                      LocalCurrency("TL", "try_kg"))
    d = tmp_path / "data"
    write_site_data(crop, tiny_tables, d, datetime(2026, 11, 17, tzinfo=timezone.utc))
    out = wbmod.build_workbook(d, tmp_path / "x.xlsx", crop, "https://example.org/")
    names = [name for name, _ in wbmod.sheet_list("hazelnut")]
    assert names == load_workbook(out).sheetnames
    assert all(note for _, note in wbmod.sheet_list("hazelnut"))


@pytest.mark.parametrize("n, text", [(900, "1 KB"), (850_000, "830 KB"),
                                     (1_300_000, "1.2 MB"), (12_000_000, "11 MB")])
def test_file_size_text(n, text):
    assert ph.file_size_text(n) == text


def test_workbook_download_html_links_the_file_or_says_it_is_missing():
    html = ph.workbook_download_html("downloads/rye-market-data.xlsx", 1_300_000)
    assert 'href="downloads/rye-market-data.xlsx"' in html and "download" in html
    assert "1.2 MB" in html and 'class="btn pri"' in html
    missing = ph.workbook_download_html("downloads/rye-market-data.xlsx", None)
    assert "href" not in missing
    assert "The workbook is not available in this refresh." in missing


def test_sheet_list_html_lists_each_sheet_with_its_note():
    html = ph.sheet_list_html([("README", "What is where"), ("Prices", "Monthly <prices>")])
    assert html.index("README") < html.index("Prices")
    assert "Monthly &lt;prices&gt;" in html
    assert 'data-quarto-disable-processing="true"' in html


def test_sources_table_html_links_each_provider_with_its_terms():
    html = ph.sources_table_html(SOURCES)
    assert '<a href="https://north.example/">North Commodity Exchange</a>' in html
    assert "CC BY 4.0" in html and "Credit the source" in html and "Weather" in html


def test_hazelnut_sources_credit_every_required_provider_with_known_terms():
    names = [s[0] for s in hazelnut_data.WORKBOOK_SOURCES]
    for want in ("UN Comtrade", "FAOSTAT", "TOBB", "Giresun Commodity Exchange",
                 "Ordu Commodity Exchange", "Open-Meteo", "ECB", "OECD"):
        assert want in names
    terms = {s[0]: s[3] for s in hazelnut_data.WORKBOOK_SOURCES}
    for cc in ("Open-Meteo", "FAOSTAT", "OECD"):
        assert terms[cc] == "CC BY 4.0"
    for other in ("UN Comtrade", "TOBB", "Giresun Commodity Exchange", "Ordu Commodity Exchange"):
        assert terms[other] == "Credit the source; see provider terms"


# --- methods ------------------------------------------------------------------------------

def _board(ratios: dict, n=(236, 234, 231)):
    rows = [(m, h, nn, r) for m, rs in ratios.items() for (h, nn, r) in zip((1, 3, 6), n, rs)]
    return pd.DataFrame(rows, columns=["method", "horizon", "n", "ratio"])


def _ranges():
    return pd.DataFrame({"method": ["naive_emp"] * 3 + ["sarima"] * 3,
                         "horizon": [1, 3, 6] * 2,
                         "cov80": [0.8178, 0.8418, 0.8312, 0.87, 0.85, 0.84]})


def test_range_held_text_is_a_span_over_horizons():
    assert ph.range_held_text(_ranges(), "naive_emp") == "82% to 84%"
    one = _ranges().assign(cov80=0.83)
    assert ph.range_held_text(one, "naive_emp") == "83%"


def test_methods_facts_agree_with_the_forecasting_page():
    dev = _board({"naive": (1, 1, 1), "sarima": (1.043, 1.019, 1.039),
                  "seasonal_naive": (1.022, 1.041, 1.031)})
    holdout = _board({"naive": (1, 1, 1), "sarima": (0.953, 1.016, 1.011)}, n=(24, 24, 24))
    facts = ph.methods_facts(dev, holdout, _ranges(), range_method="naive_emp",
                             holdout_period=("2024-10", "2026-09"))
    assert facts[0] == ("Development period, walk-forward in USD, 231 to 236 forecasts per "
                        "horizon: None beat naive at any horizon; the closest lost by 2% to 3%.")
    assert facts[1].startswith("Holdout, October 2024 to September 2026: 24 forecasts per "
                               "horizon, scored once, never tuned on.")
    assert "No method beat naive at every horizon" in facts[1]
    assert facts[2] == ("The 8-in-10 range from past price moves held 82% to 84% of the time "
                        "in the backtest, at 1, 3 and 6 months ahead.")


@pytest.mark.parametrize("lang", ["en", "tr"])
@pytest.mark.parametrize("holdout", [
    {"naive": (1, 1, 1), "sarima": (0.95, 0.96, 0.97)},   # a winner at every horizon
    {"naive": (1, 1, 1), "sarima": (1.1, 1.1, 1.1)},      # none under 1
    {"naive": (1, 1, 1), "sarima": (0.95, 1.1, 1.1)},     # some under 1, each lost elsewhere
])
def test_methods_holdout_card_names_the_holdout_once(lang, holdout, turkish):
    # Q31: the holdout line reads "<holdout>, <first> – <last>: <finding>", and no
    # finding repeats the holdout's name after the lead-in.
    from hazelnut.site import i18n

    i18n.LANG = lang
    dev = _board({"naive": (1, 1, 1), "sarima": (1.1, 1.1, 1.1)})
    facts = ph.methods_facts(dev, _board(holdout, n=(24, 24, 24)), None,
                             range_method="naive_emp", holdout_period=("2024-10", "2026-09"))
    name = {"en": "Holdout", "tr": "Ayrılmış test dönemi"}[lang]
    assert facts[1].startswith(name + ", ")
    assert facts[1].count(name) == 1, facts[1]


def test_explorer_download_months_are_in_the_page_language(turkish):
    # Q33 (B): the Turkish download's month cells name Turkish months in any Excel; the
    # English download keeps its format. The OJS cell takes it from the config.
    from hazelnut.site import i18n

    assert _cfg()["month_format"] == "[$-tr-TR]mmm yyyy"
    i18n.LANG = "en"
    assert _cfg()["month_format"] == "mmm yyyy"
    ojs = (SITE_DIR / "hazelnut" / "explorer.qmd").read_text(encoding="utf-8")
    assert "z: explorer.month_format" in ojs and '"mmm yyyy"' not in ojs


def test_methods_facts_skip_what_is_missing():
    assert ph.methods_facts(None, None, None, range_method="naive_emp",
                            holdout_period=("2024-10", "2026-09")) == []
    dev = _board({"naive": (1, 1, 1), "sarima": (1.1, 1.1, 1.1)})
    facts = ph.methods_facts(dev, None, None, range_method="naive_emp", holdout_period=None)
    assert len(facts) == 1


def test_validation_lag_is_a_named_constant():
    assert validate.MAX_LAG_MONTHS == 3


def test_explorer_ojs_has_no_interface_text_of_its_own():
    """The explorer's OJS cells take every visible string from ``explorer.ui`` (and the
    number locale from ``explorer.locale``), not from literals of their own."""
    import re

    from hazelnut.site.config import SITE_DIR

    qmd = (SITE_DIR / "hazelnut" / "explorer.qmd").read_text(encoding="utf-8")
    ojs = "\n".join(re.findall(r"```\{ojs\}(.*?)```", qmd, re.S))
    code = "\n".join(line.split("//", 1)[0] for line in ojs.splitlines())  # comments aside
    assert "en-US" not in code and "toLocaleString(explorer.locale" in code
    # A string literal or an element's text ("Latest", `Latest`, >Latest<).
    found = [text for _, text in _leaves(EN_UI) if "{" not in text
             and re.search(rf"[\"'`>]{re.escape(text)}[\"'`<]", code)]
    assert found == []

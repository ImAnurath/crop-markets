"""Plotly chart helpers for the portfolio site."""
import sys

import pandas as pd
import pytest

from hazelnut.forecast.dataset import SHOCK_PERIODS
from hazelnut.site import charts


@pytest.fixture
def prices() -> pd.DataFrame:
    months = pd.period_range("2004-01", "2026-09", freq="M").astype(str)
    n = len(months)
    return pd.DataFrame(
        {
            "month": months,
            "usd_kg": [3.0 + 0.01 * i for i in range(n)],
            "try_kg": [4.0 + 0.5 * i for i in range(n)],
        }
    )


def _button_labels(menu) -> list[str]:
    return [b.label for b in menu.buttons]


def test_price_history_has_currency_buttons(prices):
    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    assert len(fig.layout.updatemenus) == 2  # currency, then period
    assert _button_labels(fig.layout.updatemenus[0]) == ["USD", "TL"]
    assert [t.name for t in fig.data] == ["USD", "TL"]
    assert [t.visible for t in fig.data] == [True, False]


def test_price_history_takes_the_local_currency_from_the_caller(prices):
    prices = prices.rename(columns={"try_kg": "eur_kg"})
    fig = charts.price_history(prices, SHOCK_PERIODS, "eur_kg", "EUR")
    assert _button_labels(fig.layout.updatemenus[0]) == ["USD", "EUR"]
    assert [t.name for t in fig.data] == ["USD", "EUR"]
    assert fig.layout.yaxis2.ticksuffix == " EUR"
    assert list(fig.data[1].y) == list(prices["eur_kg"])
    assert "EUR/kg" in fig.data[1].hovertemplate


def test_price_history_local_view_uses_a_log_axis(prices):
    # Nominal lira prices are flat for decades then explode; a log axis keeps both readable.
    # USD sits on yaxis (linear), the local currency on yaxis2 (log); the currency buttons
    # only swap which trace and axis are visible.
    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    assert [t.yaxis for t in fig.data] == ["y", "y2"]
    assert fig.layout.yaxis.type == "linear" and fig.layout.yaxis2.type == "log"
    assert fig.layout.yaxis2.overlaying == "y" and fig.layout.yaxis2.visible is False
    # its own round log ticks (1, 2, 5 x 10^n), not synced to the USD axis
    assert fig.layout.yaxis2.tickmode == "linear" and fig.layout.yaxis2.dtick == "D2"
    # ticks carry the currency; the USD ticks keep their "$"
    assert fig.layout.yaxis2.ticksuffix == " TL" and fig.layout.yaxis.tickprefix == "$"
    usd, local = fig.layout.updatemenus[0].buttons
    assert list(usd.args) == [{"visible": [True, False]}, {"yaxis.visible": True, "yaxis2.visible": False}]
    assert list(local.args) == [{"visible": [False, True]}, {"yaxis.visible": False, "yaxis2.visible": True}]


def test_price_history_hover_shows_the_date_once(prices):
    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    assert fig.layout.hovermode == "x unified"  # the month is the hover box's title
    assert fig.layout.xaxis.hoverformat == "%b %Y"
    assert all("%{x" not in t.hovertemplate for t in fig.data)


def test_price_history_has_period_buttons(prices):
    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    menu = fig.layout.updatemenus[1]
    assert _button_labels(menu) == ["5y", "10y", "All"]
    assert menu.active == 2
    assert fig.layout.xaxis.rangeselector.buttons == ()  # no rangeselector: it can't set y


def test_price_history_period_buttons_rescale_y_to_the_window():
    # USD: 10 everywhere except one early spike of 50; local: 1 rising to 1000.
    months = pd.period_range("2000-01", "2020-12", freq="M").astype(str)
    n = len(months)
    usd = [10.0] * n
    usd[12] = 50.0  # 2001-01, outside the 5y and 10y windows
    usd[-1] = 12.0  # 2020-12
    local = [10 ** (3 * i / (n - 1)) for i in range(n)]  # 1 .. 1000, log-linear
    prices = pd.DataFrame({"month": months, "usd_kg": usd, "try_kg": local})
    fig = charts.price_history(prices, [], "try_kg", "TL")
    ranges = {b.label: b.args[0] for b in fig.layout.updatemenus[1].buttons}
    assert all(b.method == "relayout" for b in fig.layout.updatemenus[1].buttons)

    assert ranges["5y"]["xaxis.range"] == ["2015-12-01", "2020-12-01"]
    assert ranges["All"]["xaxis.range"] == ["2000-01-01", "2020-12-01"]
    # USD: 10..12 inside 5y (padded 5% of the span), 10..50 for All
    assert ranges["5y"]["yaxis.range"] == pytest.approx([9.9, 12.1])
    assert ranges["All"]["yaxis.range"] == pytest.approx([8.0, 52.0])
    # local: log10 units; All spans 0..3, 5y covers only the last 61 months
    assert ranges["All"]["yaxis2.range"] == pytest.approx([-0.15, 3.15])
    lo5 = 3 * (n - 61) / (n - 1)
    assert ranges["5y"]["yaxis2.range"] == pytest.approx([lo5 - (3 - lo5) * 0.05, 3 + (3 - lo5) * 0.05])
    assert ranges["10y"]["yaxis2.range"][0] < ranges["5y"]["yaxis2.range"][0]
    # the chart opens on All
    assert list(fig.layout.yaxis.range) == pytest.approx(ranges["All"]["yaxis.range"])
    assert list(fig.layout.yaxis2.range) == pytest.approx(ranges["All"]["yaxis2.range"])
    assert list(fig.layout.xaxis.range) == ranges["All"]["xaxis.range"]


def test_price_windows_ignore_gaps_and_non_positive_log_values():
    x = pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"])
    out = charts.price_windows(x, pd.Series([1.0, None, 3.0]), pd.Series([0.0, 10.0, 100.0]))
    label, xr, yr, y2r = out[-1]
    assert label == "All" and yr == pytest.approx([0.9, 3.1])
    assert y2r == pytest.approx([0.95, 2.05])  # the 0 is left out of the log range


def test_price_history_shades_each_shock(prices):
    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    rects = [s for s in fig.layout.shapes if s.type == "rect"]
    assert len(rects) == len(SHOCK_PERIODS) == 3
    assert all(s.fillcolor == charts.ACCENT for s in rects)


def test_layout_is_transparent():
    lay = charts.layout()
    assert lay["paper_bgcolor"] == "rgba(0,0,0,0)"
    assert lay["plot_bgcolor"] == "rgba(0,0,0,0)"
    assert "Geist" in lay["font"]["family"]


def test_layout_overrides_merge_nested_keys():
    lay = charts.layout(margin={"t": 40}, height=300)
    assert lay["margin"]["t"] == 40
    assert lay["margin"]["l"] == charts.layout()["margin"]["l"]
    assert lay["height"] == 300


def test_price_range_fig_has_band_and_today_marker():
    rng = pd.DataFrame(
        {
            "horizon": [1, 3, 6],
            "target_month": ["2026-10", "2026-12", "2027-03"],
            "q05": [3.7, 3.2, 2.8], "q10": [3.9, 3.4, 3.1], "q50": [4.3, 4.3, 4.4],
            "q90": [4.8, 5.4, 6.0], "q95": [5.1, 5.8, 6.7],
            "from_month": ["2026-09"] * 3, "from_usd": [4.28] * 3,
        }
    )
    fig = charts.price_range_fig(rng)
    xs = [list(t.x) for t in fig.data if t.x is not None]
    # every trace starts at today's month
    assert all(x[0] == "2026-09" for x in xs)
    assert any(t.marker.color == charts.ACCENT for t in fig.data if t.mode and "markers" in t.mode)


def test_bar_top_is_sorted_horizontal_bars():
    top = pd.DataFrame(
        {"partner": ["Italy", "Germany", "France"], "net_kg": [3.0, 2.0, 1.0],
         "fob_usd": [30.0, 20.0, 10.0], "share": [0.5, 0.3, 0.2]}
    )
    fig = charts.bar_top(top)
    bar = fig.data[0]
    assert bar.orientation == "h"
    # largest at the top: plotly draws categories bottom-up, so reverse order
    assert list(bar.y) == ["France", "Germany", "Italy"]


def test_bar_top_puts_other_last_even_when_it_is_large():
    top = pd.DataFrame(
        {"partner": ["Italy", "Other", "Germany", "France"], "net_kg": [3.0, 2.5, 2.0, 1.0],
         "fob_usd": [30.0, 25.0, 20.0, 10.0], "share": [0.35, 0.3, 0.23, 0.12]}
    )
    bar = charts.bar_top(top).data[0]
    # bottom-up: "Other" is drawn last (at the bottom), the rest largest at the top
    assert list(bar.y) == ["Other", "France", "Germany", "Italy"]
    assert list(bar.x) == [0.3, 0.12, 0.23, 0.35]


def test_crop_vs_price_highlights_latest_year_in_accent():
    crop = pd.DataFrame(
        {
            "year": [2022, 2023, 2024, 2025, 2026],
            "season": ["2022/23", "2023/24", "2024/25", "2025/26", "2026/27"],
            "giresun_estimate_t": [100.0, 90.0, 80.0, 60.0, 86.0],
            "giresun_registered_t": [None] * 5,
            "national_estimate_t": [None] * 5,
            "season_avg_usd": [None, 3.2, 3.5, 6.0, 4.3],
        }
    )
    fig = charts.crop_vs_price(crop, "giresun_estimate_t", "Giresun crop estimate")
    accent = [t for t in fig.data if t.marker.color == charts.ACCENT]
    assert len(accent) == 1
    assert "2026" in accent[0].name
    assert list(accent[0].x) == [86.0]
    # rows without a season price are dropped, the rest drawn in the neutral colour
    others = [t for t in fig.data if t is not accent[0]]
    assert sum(len(t.x) for t in others) == 3
    assert fig.layout.xaxis.title.text == "Giresun crop estimate"


def test_crop_vs_price_with_no_complete_rows_is_an_empty_figure():
    crop = pd.DataFrame(
        {"year": [2025, 2026], "season": ["2025/26", "2026/27"],
         "giresun_estimate_t": [60.0, None], "season_avg_usd": [None, 4.3]}
    )
    fig = charts.crop_vs_price(crop, "giresun_estimate_t", "Giresun crop estimate")
    assert len(fig.data) == 0
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"


def test_crop_vs_price_requires_the_crop_column():
    import inspect

    assert inspect.signature(charts.crop_vs_price).parameters["x_col"].default is inspect.Parameter.empty


def test_charts_does_not_import_torch():
    import subprocess

    code = (
        "import sys, hazelnut.site.charts; "
        "bad=[m for m in ('torch','chronos','hazelnut.forecast.methods.chronos') if m in sys.modules]; "
        "sys.exit(1 if bad else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_to_html_embeds_figure_json_for_site_js(prices):
    import json
    import re

    from plotly.offline import get_plotlyjs_version

    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    fig.update_layout(meta="</script><b>")  # must not end the JSON block early
    html = charts.to_html(fig)
    assert html.count("</script>") == 1
    m = re.search(r'<script type="application/json">(.*)</script>', html, re.S)
    spec = json.loads(m.group(1))
    assert [t["name"] for t in spec["data"]] == ["USD", "TL"]
    assert spec["layout"]["meta"] == "</script><b>"
    assert spec["config"] == charts.CONFIG
    # site.js loads the plotly.js build that matches this plotly.py, with SRI
    assert f'data-plotly-src="https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"' in html
    assert 'data-plotly-sri="sha256-' in html
    # a sized loading skeleton until site.js draws it
    assert 'class="chart chart-skeleton"' in html
    assert "height:360px" in html


def test_show_emits_a_raw_html_block_not_text_html(prices, monkeypatch):
    # text/html cell outputs make Quarto add require.js + a second jQuery to the page;
    # a markdown raw-HTML block passes through untouched without them.
    import IPython.display

    shown = []
    monkeypatch.setattr(IPython.display, "display", lambda obj: shown.append(obj))
    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    charts.show(fig)
    (obj,) = shown
    assert isinstance(obj, IPython.display.Markdown)
    assert obj.data == "```{=html}\n" + charts.to_html(fig) + "\n```\n"


def _spec(html: str) -> dict:
    import json
    import re

    return json.loads(re.search(r'<script type="application/json">(.*)</script>', html, re.S)[1])


def test_english_charts_carry_no_locale(prices):
    spec = _spec(charts.to_html(charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")))
    assert spec["config"] == charts.CONFIG
    assert "separators" not in spec["layout"]


def test_turkish_charts_get_plotlys_tr_locale_and_separators(prices, turkish):
    from hazelnut.site.plotly_locales import LOCALES

    spec = _spec(charts.to_html(charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")))
    assert spec["layout"]["separators"] == ",."  # decimal comma, thousands dot
    assert spec["config"] == {**charts.CONFIG, "locale": "tr", "locales": {"tr": LOCALES["tr"]}}
    assert LOCALES["tr"]["format"]["shortMonths"][9] == "Eki"  # hover "%b %Y" -> "Eki 2026"


def test_turkish_price_history_labels(prices, turkish):
    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    assert _button_labels(fig.layout.updatemenus[1]) == ["5Y", "10Y", "Tümü"]
    assert fig.data[0].hovertemplate == "%{y:.2f} $/kg<extra></extra>"  # "4,13 $/kg"
    assert fig.layout.yaxis.ticksuffix == " $" and fig.layout.yaxis.tickprefix is None


def test_plotly_locales_match_bundled_plotlyjs():
    # The locale data is copied from the plotly.js that plotly.py bundles; re-copy it
    # (src/hazelnut/site/plotly_locales.py) when the pinned plotly changes.
    from plotly.offline import get_plotlyjs_version

    from hazelnut.site.plotly_locales import PLOTLY_JS_VERSION

    assert get_plotlyjs_version() == PLOTLY_JS_VERSION


# --- every chart in Turkish -------------------------------------------------------------

def _page_label(key: str) -> str:
    """A label a page passes to a chart builder (site/i18n "hazelnut.chart.*")."""
    from hazelnut.site.i18n import t

    return t(f"hazelnut.chart.{key}")


def _all_figures(prices) -> dict:
    """Every chart builder, called the way the pages call it (labels from site/i18n)."""
    import numpy as np

    from hazelnut.site.i18n import t
    from hazelnut.site.labels import OTHER_PARTNER, method_name

    months = ["2005-01", "2005-02", "2005-03"]
    rng = pd.DataFrame({"horizon": [1, 3], "target_month": ["2026-10", "2026-12"],
                        "q05": [3.7, 3.2], "q10": [3.9, 3.4], "q50": [4.3, 4.3],
                        "q90": [4.8, 5.4], "q95": [5.1, 5.8],
                        "from_month": ["2026-09"] * 2, "from_usd": [4.28] * 2})
    top = pd.DataFrame({"partner": ["İtalya", OTHER_PARTNER], "net_kg": [3e6, 1e6],
                        "fob_usd": [3e7, 1e7], "share": [0.31, 0.69]})
    crop = pd.DataFrame({"year": [2024, 2025], "season": ["2024/25", "2025/26"],
                         "giresun_estimate_t": [600000.0, 650000.0],
                         "season_avg_usd": [4.1, 3.9]})
    prof = pd.DataFrame({"month": [9, 10], "label": ["Eylül", "Ekim"], "mean": [-0.035, 0.02],
                         "q25": [-0.1, -0.05], "q75": [0.02, 0.05], "seasons": [3, 3]})
    f3 = pd.DataFrame({"target_month": months[:2], "actual": [4.7, 4.8], "naive": [4.1, 5.3],
                       "best_other": [4.15, 5.31]})
    band = pd.DataFrame({"target_month": months, "actual": [4.0, 7.0, 5.0],
                         "q10": [3.0, 3.0, 5.0], "q90": [5.0, 5.0, 6.0]})
    scatter = pd.DataFrame({"year": [2004, 2014], "frost_days": [8.7, 2.3],
                            "crop_t": [11480.0, 24456.0]})
    wide = pd.DataFrame({_page_label("calm_months"): [1.02, 0.99],
                         _page_label("lira_crises"): [0.93, 0.61]}, index=[1, 3])
    crop_label = t("crop_estimate.label_no_year", source="Giresun")
    return {
        "price_history": charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL"),
        "price_range_fig": charts.price_range_fig(rng),
        "bar_top": charts.bar_top(top),
        "crop_vs_price": charts.crop_vs_price(crop, "giresun_estimate_t", crop_label),
        "season_profile": charts.season_profile(prof),
        "share_lines": charts.share_lines(pd.DataFrame({"İtalya": [0.1, 0.3]}, index=[2000, 2025])),
        "compare_lines": charts.compare_lines(months, [1.0, 2.0, 3.0], [1.0, np.nan, 2.0],
                                              _page_label("shelled_exports"),
                                              _page_label("giresun_in_shell")),
        "gap_line": charts.gap_line(months, [-0.1, -0.2, 0.0], median=-0.1),
        "labeled_scatter": charts.labeled_scatter(
            scatter, "frost_days", "crop_t", "year", highlight=[2004],
            x_title=_page_label("frost_days"), y_title=crop_label,
            y_suffix=" " + t("unit.tonnes")),
        "forecast_vs_actual": charts.forecast_vs_actual(f3, method_name("season_reg")),
        "range_band": charts.range_band(band),
        "ratio_bars": charts.ratio_bars(wide, highlight=_page_label("lira_crises")),
    }


# Figure keys whose strings a reader sees (legend, hover, bar and tick labels, buttons,
# axis titles); "text" also covers axis titles ({"title": {"text": ...}}).
_VISIBLE = {"name", "hovertemplate", "texttemplate", "text", "ticktext", "label", "tickprefix",
            "ticksuffix", "customdata"}


def _visible_strings(node, seen: bool = False) -> list[str]:
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in _visible_strings(v, seen or k in _VISIBLE)]
    if isinstance(node, (list, tuple)):
        return [s for v in node for s in _visible_strings(v, seen)]
    return [node] if seen and isinstance(node, str) else []


def _words(text: str) -> set[str]:
    import re

    text = re.sub(r"%\{[^}]*\}|\{\w+\}|<[^>]*>", " ", text)  # placeholders and tags
    return {w.lower() for w in re.findall(r"[^\W\d_]{2,}", text)}


# The site/i18n strings charts show, and the chart labels pages pass in.
_CHART_KEYS = ("chart.", "method.", "exports.other", "unit.mo", "unit.tonnes",
               "season.to_date_label", "crop_estimate.label", "hazelnut.chart.")


def _english_chart_words() -> set[str]:
    """Words of the English chart strings that their Turkish strings do not also use
    (USD, kg, SARIMA, Giresun... read the same in both)."""
    from hazelnut.site import i18n

    en, tr = i18n.strings("en"), i18n.strings("tr")
    keys = [k for k in en if k.startswith(_CHART_KEYS)]
    shared = set().union(*(_words(tr[k]) for k in keys))
    return set().union(*(_words(en[k]) for k in keys)) - shared


def _figure_words(figs: dict) -> dict[str, set[str]]:
    return {name: set().union(*map(_words, _visible_strings(fig.to_plotly_json())))
            for name, fig in figs.items()}


def test_chart_strings_have_turkish_drafts():
    from hazelnut.site import i18n

    todo = [k for k, v in i18n.strings("tr").items()
            if k.startswith(_CHART_KEYS) and v == i18n.TODO]
    assert todo == []


def test_turkish_figures_contain_no_english_template_words(prices, monkeypatch):
    from hazelnut.site import i18n

    english = _english_chart_words()
    # The check bites: built in English, every figure but one shows these words (the
    # share lines show only partner names, which are data).
    en_hits = {k: w & english for k, w in _figure_words(_all_figures(prices)).items()}
    assert [k for k, v in en_hits.items() if not v] == ["share_lines"]

    monkeypatch.setattr(i18n, "LANG", "tr")
    tr_hits = {k: w & english for k, w in _figure_words(_all_figures(prices)).items()}
    assert {k: v for k, v in tr_hits.items() if v} == {}


def test_every_turkish_chart_gets_the_tr_locale_and_separators(prices, turkish):
    for name, fig in _all_figures(prices).items():
        spec = _spec(charts.to_html(fig))
        assert spec["layout"]["separators"] == ",.", name
        assert spec["config"]["locale"] == "tr", name


def test_turkish_percents_put_the_sign_first(prices, turkish):
    figs = _all_figures(prices)
    bar = figs["bar_top"].data[0]
    assert bar.texttemplate == "%{text}" and list(bar.text) == ["%69", "%31"]  # bottom-up
    assert "%{customdata[2]}" in bar.hovertemplate and bar.customdata[1][2] == "%31,0"

    season = figs["season_profile"]
    assert season.layout.yaxis.tickformat is None
    assert {"−%10", "%0", "+%4"} <= set(season.layout.yaxis.ticktext)
    assert list(season.data[0].customdata[0][3:]) == ["−%3,5", "−%10,0", "+%2,0"]
    assert "%{customdata[3]}" in season.data[0].hovertemplate

    gap = figs["gap_line"]
    assert {"−%20", "−%10", "%0"} <= set(gap.layout.yaxis.ticktext)
    assert list(gap.data[0].customdata) == ["−%10,0", "−%20,0", "%0,0"]
    assert gap.data[0].hovertemplate == "%{customdata}<extra></extra>"
    assert gap.data[1].name == "Medyan −%10,0"

    share = figs["share_lines"]
    assert share.layout.yaxis.ticktext[:2] == ("%0", "%5")
    assert list(share.data[0].customdata) == ["%10", "%30"]
    assert share.data[0].hovertemplate == "İtalya %{customdata}<extra></extra>"


def test_turkish_percent_ticks_sit_on_round_values(turkish):
    ticks = charts._pct_axis(-0.034, 0.081, signed=True)
    assert ticks["tickmode"] == "array"
    assert ticks["tickvals"] == [-0.04, -0.02, 0.0, 0.02, 0.04, 0.06, 0.08, 0.1]
    assert ticks["ticktext"][:3] == ["−%4", "−%2", "%0"]
    fine = charts._pct_axis(0.0, 0.012)  # steps under one percent get a decimal
    assert fine["ticktext"][:3] == ["%0,0", "%0,2", "%0,4"]


def test_turkish_tonne_axes_write_thousands_in_full(prices, turkish):
    figs = _all_figures(prices)
    assert figs["crop_vs_price"].layout.xaxis.tickformat == ",.0f"  # 650.000 t, not 650k t
    assert figs["labeled_scatter"].layout.yaxis.tickformat == ",.0f"


def test_english_percents_stay_plotly_formats(prices):
    figs = _all_figures(prices)
    assert figs["bar_top"].data[0].texttemplate == "%{x:.0%}"
    assert "%{x:.1%} of exports" in figs["bar_top"].data[0].hovertemplate
    assert figs["season_profile"].layout.yaxis.tickformat == "+.0%"
    assert "average %{y:+.1%}" in figs["season_profile"].data[0].hovertemplate
    assert figs["gap_line"].layout.yaxis.tickformat == "+.0%"
    assert figs["share_lines"].layout.yaxis.tickformat == ".0%"
    assert figs["share_lines"].data[0].hovertemplate == "İtalya %{y:.0%}<extra></extra>"
    assert figs["crop_vs_price"].layout.xaxis.tickformat == "~s"


def test_destination_names_are_turkish_in_turkish_charts(turkish):
    top = pd.DataFrame({"partner": ["Italy", "Germany", "Other"], "net_kg": [3e7, 2e7, 1e7],
                        "fob_usd": [1, 1, 1], "share": [0.5, 0.3, 0.2]})
    assert list(charts.bar_top(top).data[0].y) == ["Diğer", "Almanya", "İtalya"]
    fig = charts.share_lines(pd.DataFrame({"Italy": [0.1, 0.3]}, index=[2000, 2025]),
                             highlight="Italy")
    line = fig.data[0]
    assert line.name == "İtalya" and line.text[-1] == "İtalya"
    assert line.hovertemplate.startswith("İtalya ") and line.meta == "accent"


def test_destination_names_are_unchanged_in_english_charts():
    top = pd.DataFrame({"partner": ["Italy", "Other"], "net_kg": [3e7, 1e7],
                        "fob_usd": [1, 1], "share": [0.6, 0.4]})
    assert list(charts.bar_top(top).data[0].y) == ["Other", "Italy"]

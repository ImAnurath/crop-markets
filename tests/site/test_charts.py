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
    assert len(fig.layout.updatemenus) == 1
    assert _button_labels(fig.layout.updatemenus[0]) == ["USD", "TL"]
    assert [t.name for t in fig.data] == ["USD", "TL"]
    assert [t.visible for t in fig.data] == [True, False]


def test_price_history_takes_the_local_currency_from_the_caller(prices):
    prices = prices.rename(columns={"try_kg": "eur_kg"})
    fig = charts.price_history(prices, SHOCK_PERIODS, "eur_kg", "EUR")
    assert _button_labels(fig.layout.updatemenus[0]) == ["USD", "EUR"]
    assert [t.name for t in fig.data] == ["USD", "EUR"]
    assert list(fig.data[1].y) == list(prices["eur_kg"])
    assert "EUR/kg" in fig.data[1].hovertemplate


def test_price_history_local_view_uses_a_log_axis(prices):
    # Nominal lira prices are flat for decades then explode; a log axis keeps both readable.
    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    usd, local = fig.layout.updatemenus[0].buttons
    assert usd.args[1]["yaxis.type"] == "linear"
    assert local.args[1]["yaxis.type"] == "log"
    assert fig.layout.yaxis.type in (None, "linear")


def test_price_history_has_period_buttons(prices):
    fig = charts.price_history(prices, SHOCK_PERIODS, "try_kg", "TL")
    labels = [b.label for b in fig.layout.xaxis.rangeselector.buttons]
    assert labels == ["5y", "10y", "All"]


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
    fig = charts.crop_vs_price(crop, "giresun_estimate_t")
    accent = [t for t in fig.data if t.marker.color == charts.ACCENT]
    assert len(accent) == 1
    assert "2026" in accent[0].name
    assert list(accent[0].x) == [86.0]
    # rows without a season price are dropped, the rest drawn in the neutral colour
    others = [t for t in fig.data if t is not accent[0]]
    assert sum(len(t.x) for t in others) == 3


def test_crop_vs_price_with_no_complete_rows_is_an_empty_figure():
    crop = pd.DataFrame(
        {"year": [2025, 2026], "season": ["2025/26", "2026/27"],
         "giresun_estimate_t": [60.0, None], "season_avg_usd": [None, 4.3]}
    )
    fig = charts.crop_vs_price(crop, "giresun_estimate_t")
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

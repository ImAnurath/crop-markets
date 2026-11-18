"""Chart helpers for the analyses pages: roles for site.js theming, data, and no titles."""
import numpy as np
import pandas as pd
import pytest

from hazelnut.site import charts


def _no_title(fig):
    assert not (fig.layout.title and fig.layout.title.text)


def _roles(fig):
    return [t.meta for t in fig.data]


def test_season_profile_bars_and_middle_half_whiskers():
    prof = pd.DataFrame({"month": [9, 10, 11], "label": ["September", "October", "November"],
                         "mean": [-0.03, 0.0, 0.03], "q25": [-0.1, -0.05, -0.02],
                         "q75": [0.02, 0.05, 0.1], "seasons": [3, 3, 3]})
    fig = charts.season_profile(prof)
    _no_title(fig)
    bars, whiskers = fig.data
    assert bars.type == "bar" and list(bars.x) == ["Sep", "Oct", "Nov"]
    assert list(bars.y) == [-0.03, 0.0, 0.03]
    assert _roles(fig) == ["fg", "fg"]
    # one vertical segment per month, separated by None
    assert list(whiskers.y) == [-0.1, 0.02, None, -0.05, 0.05, None, -0.02, 0.1, None]
    assert fig.layout.yaxis.tickformat.endswith("%")


def test_share_lines_one_line_per_partner_with_end_labels_and_highlight():
    shares = pd.DataFrame({"Italy": [0.1, 0.3], "Germany": [0.4, 0.2]}, index=[2000, 2025])
    fig = charts.share_lines(shares, highlight="Italy")
    _no_title(fig)
    assert [t.name for t in fig.data] == ["Italy", "Germany"]
    assert _roles(fig) == ["accent", "fg"]
    assert all("text" in t.mode for t in fig.data)
    assert list(fig.data[1].text) == ["", "Germany"]  # label at the last point only


def test_compare_lines_keeps_gaps_and_styles_the_second_line():
    x = ["2000-01", "2000-02", "2000-03"]
    fig = charts.compare_lines(x, [1.0, 2.0, 3.0], [1.0, np.nan, 2.0], "Giresun", "Ordu")
    _no_title(fig)
    a, b = fig.data
    assert (a.name, b.name) == ("Giresun", "Ordu")
    assert _roles(fig) == ["fg", "fg"]
    assert b.connectgaps is False and b.line.dash == "dot"
    assert fig.layout.hovermode == "x unified"
    assert fig.layout.showlegend is True


def test_compare_lines_shades_shocks():
    fig = charts.compare_lines(["2005-01", "2005-02"], [1, 2], [1, 2], "a", "b",
                               shocks=[("2005-01", "2005-12")])
    assert [s.name for s in fig.layout.shapes] == ["shock"]


def test_gap_line_has_zero_and_median_reference():
    fig = charts.gap_line(["2000-01", "2000-02", "2000-03"], [-0.1, -0.2, 0.0], median=-0.1)
    _no_title(fig)
    assert fig.data[0].meta == "fg"
    ref = [t for t in fig.data if t.name and t.name.startswith("Median")]
    assert len(ref) == 1 and ref[0].meta == "accent" and set(ref[0].y) == {-0.1}
    assert fig.layout.yaxis.tickformat.endswith("%")


def test_labeled_scatter_labels_highlighted_points_in_amber():
    df = pd.DataFrame({"year": [2003, 2004, 2014], "frost_days": [15.0, 8.7, 2.3],
                       "crop_t": [76404.0, 11480.0, 24456.0]})
    fig = charts.labeled_scatter(df, "frost_days", "crop_t", "year", highlight=[2004, 2014],
                                 x_title="Frost days", y_title="Crop")
    _no_title(fig)
    rest, hl = fig.data
    assert (rest.meta, hl.meta) == ("fg", "accent")
    assert list(hl.text) == ["2004", "2014"] and "text" in hl.mode
    assert list(rest.x) == [15.0]


def test_labeled_scatter_drops_incomplete_rows():
    df = pd.DataFrame({"year": [1, 2], "a": [1.0, np.nan], "b": [2.0, 3.0]})
    fig = charts.labeled_scatter(df, "a", "b", "year")
    assert sum(len(t.x) for t in fig.data) == 1


def _f3():
    return pd.DataFrame({"target_month": ["2005-04", "2005-05"], "actual": [4.7, 4.8],
                         "naive": [4.1, 5.3], "best_other": [4.15, 5.31],
                         "best_other_method": ["sarima", "sarima"]})


def test_forecast_vs_actual_three_lines_naive_in_amber():
    fig = charts.forecast_vs_actual(_f3(), "SARIMA", shocks=[("2005-01", "2005-12")])
    _no_title(fig)
    assert [t.name for t in fig.data] == ["Actual", "Naive", "SARIMA"]
    assert _roles(fig) == ["fg", "accent", "fg"]
    assert fig.data[2].line.dash == "dot"
    assert [s.name for s in fig.layout.shapes] == ["shock"]


def test_range_band_fills_between_q10_and_q90_and_marks_misses():
    band = pd.DataFrame({"target_month": ["2005-04", "2005-05", "2005-06"],
                         "actual": [4.0, 7.0, 5.0], "q10": [3.0, 3.0, 5.0],
                         "q90": [5.0, 5.0, 6.0]})
    fig = charts.range_band(band)
    _no_title(fig)
    roles = _roles(fig)
    assert roles[:2] == ["accent-fill", "accent-fill"] and fig.data[1].fill == "tonexty"
    miss = [t for t in fig.data if t.name == "Outside the range"][0]
    assert miss.meta == "accent" and list(miss.y) == [7.0]  # 5.0 on the edge counts as held
    assert [t for t in fig.data if t.name == "Actual"][0].meta == "fg"


def test_ratio_bars_grouped_with_a_line_at_one():
    wide = pd.DataFrame({"calm": [1.02, 1.01, 0.99], "crisis": [0.93, 0.74, 0.61]},
                        index=[1, 3, 6])
    fig = charts.ratio_bars(wide, highlight="crisis")
    _no_title(fig)
    assert [t.name for t in fig.data] == ["calm", "crisis"]
    assert _roles(fig) == ["fg", "accent"]
    assert list(fig.data[0].x) == ["1 mo", "3 mo", "6 mo"]
    assert fig.layout.barmode == "group"
    assert fig.layout.shapes[0].y0 == 1 and fig.layout.shapes[0].y1 == 1


@pytest.mark.parametrize("make", [
    lambda: charts.season_profile(pd.DataFrame({"month": [9], "label": ["September"],
                                                "mean": [0.0], "q25": [0.0], "q75": [0.0],
                                                "seasons": [1]})),
    lambda: charts.forecast_vs_actual(_f3(), "SARIMA"),
])
def test_new_charts_render_through_to_html(make):
    html = charts.to_html(make())
    assert "data-plotly" in html and "<script type=\"application/json\">" in html


def test_gap_line_keeps_missing_months_as_gaps():
    fig = charts.gap_line(["2000-01", "2000-02", "2000-05"], [-0.1, -0.2, 0.0], median=-0.1)
    y = list(fig.data[0].y)
    assert len(y) == 5 and y[2] is None and y[3] is None

"""Analyses-page helpers in page_helpers: computed takeaways and tables for
seasonality, exports, crop and frost, exchanges and forecasting."""
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from hazelnut.site import page_helpers as ph


def _months(start: str, n: int) -> list[str]:
    return [str(p) for p in pd.period_range(start, periods=n, freq="M")]


def _season_of(month: str) -> str:
    y, m = int(month[:4]), int(month[5:])
    start = y if m >= 9 else y - 1
    return f"{start}/{str(start + 1)[2:]}"


# --- analyses index and page head -------------------------------------------------------

def test_analyses_list_links_each_slug_in_order_with_its_summary():
    html = ph.analyses_list_html(
        ["b-two", "a-one"],
        {"a-one": ("First", "One <thing>."), "b-two": ("Second", "Two things.")},
    )
    assert html.index('href="b-two.qmd"') < html.index('href="a-one.qmd"')
    assert "Second" in html and "Two things." in html
    assert "One &lt;thing&gt;." in html
    assert html.count('class="panel analysis-card"') == 2


def test_analyses_list_unknown_slug_gets_a_readable_title_and_no_summary():
    html = ph.analyses_list_html(["crop-and-frost"], {})
    assert 'href="crop-and-frost.qmd"' in html
    assert "Crop and frost" in html
    assert "<p>" not in html


def test_analysis_head_has_eyebrow_link_h1_and_what_we_found():
    html = ph.analysis_head_html("Hazelnut", "Seasonality", "When <prices> peak",
                                 "Small & steady.", stamp="Data as of May 2026")
    assert 'href="index.qmd">Analyses</a>' in html
    assert "Crops / Hazelnut /" in html and "/ Seasonality" in html
    assert "<h1>When &lt;prices&gt; peak</h1>" in html
    assert "What we found" in html and "Small &amp; steady." in html
    assert "Data as of May 2026" in html


# --- seasonality ------------------------------------------------------------------------

def _season_prices(seasons: int, bump: dict[int, float], partial_tail: int = 0) -> pd.DataFrame:
    """Flat 2.0 USD per season (level changes by season), times (1 + bump[month])."""
    months = _months("2000-09", 12 * seasons + partial_tail)
    rows = []
    for i, m in enumerate(months):
        level = 2.0 + 0.5 * (i // 12)
        rows.append((m, _season_of(m), level * (1 + bump.get(int(m[5:]), 0.0))))
    return pd.DataFrame(rows, columns=["month", "season", "usd_kg"])


def test_seasonal_profile_is_percent_from_each_season_mean_in_season_order():
    bump = {5: 0.06, 9: -0.06}  # May up, September down; the rest flat
    prof = ph.seasonal_profile(_season_prices(3, bump), "usd_kg")
    assert list(prof["month"]) == [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
    assert list(prof["label"])[:2] == ["September", "October"]
    # mean of the season's 12 values is level * 1.0 (the bumps cancel)
    assert prof.set_index("month").loc[5, "mean"] == pytest.approx(0.06)
    assert prof.set_index("month").loc[9, "mean"] == pytest.approx(-0.06)
    assert prof.set_index("month").loc[1, "mean"] == pytest.approx(0.0)
    assert set(prof["seasons"]) == {3}


def test_seasonal_profile_uses_complete_seasons_only():
    df = _season_prices(3, {5: 0.06, 9: -0.06}, partial_tail=4)  # 4 months of a 4th season
    df.loc[5, "usd_kg"] = np.nan  # season 1 now has a gap: not complete
    prof = ph.seasonal_profile(df, "usd_kg")
    assert set(prof["seasons"]) == {2}


def test_seasonality_subtitle_names_the_low_and_high_months():
    prof = ph.seasonal_profile(_season_prices(3, {5: 0.045, 9: -0.032, 1: -0.013}), "usd_kg")
    sub = ph.seasonality_subtitle(prof)
    assert "3 complete seasons" in sub
    assert "September" in sub and "May" in sub
    assert "−3.2%" in sub and "+4.5%" in sub


# --- exports ----------------------------------------------------------------------------

def _exports() -> pd.DataFrame:
    rows = []
    for m in _months("2000-01", 24) + _months("2002-01", 6):  # 2002 is partial
        y = int(m[:4])
        a = 100.0 if y == 2000 else 300.0
        for partner, kg in {"A": a, "B": 200.0, "C": 50.0, "World": a + 250.0}.items():
            rows.append((m, "shelled", partner, kg, kg * 5))
        rows.append((m, "in_shell", "A", 999.0, 1.0))
    return pd.DataFrame(rows, columns=["month", "product", "partner", "net_kg", "fob_usd"])


def test_yearly_shares_complete_years_top_partners_by_latest_year():
    shares = ph.yearly_shares(_exports(), "shelled", top=2)
    assert list(shares.index) == [2000, 2001]  # 2002 has 6 months only
    assert list(shares.columns) == ["A", "B"]  # ranked by the latest complete year
    assert shares.loc[2000, "A"] == pytest.approx(100 / 350)
    assert shares.loc[2001, "A"] == pytest.approx(300 / 550)


def test_share_shift_subtitle_from_first_to_last_year():
    shares = ph.yearly_shares(_exports(), "shelled", top=2)
    sub = ph.share_shift_subtitle(shares, "shelled export volume")
    assert sub.startswith("A's share of shelled export volume went from 29% in 2000 to 55% in 2001")
    assert "B's from 57% to 36%" in sub


def test_ratio_subtitle_median_and_8_in_10_band():
    a = pd.Series([2.0, 2.2, 1.8, 2.0, 2.0, 2.4, 2.0, 1.6, 2.0, 2.0, np.nan])
    b = pd.Series([1.0] * 11)
    stats = ph.ratio_stats(a, b)
    assert stats.n == 10 and stats.median == pytest.approx(2.0)
    sub = ph.ratio_subtitle(stats, "Shelled exports", "the exchange price")
    assert sub.startswith("Shelled exports sold for a median 2.00 times the exchange price")
    assert "8 in 10 months between" in sub


# --- exchanges --------------------------------------------------------------------------

def test_gap_series_aligns_months_and_skips_gaps():
    a = pd.DataFrame({"month": ["2000-01", "2000-02", "2000-03"], "p": [10.0, 10.0, 10.0]})
    b = pd.DataFrame({"month": ["2000-02", "2000-03", "2000-04"], "p": [9.0, np.nan, 8.0]})
    gap = ph.gap_series(a, b, "p")
    assert list(gap["month"]) == ["2000-02"]
    assert gap["gap"].iloc[0] == pytest.approx(-0.1)


def test_gap_subtitle_below_and_mixed_band():
    gap = pd.DataFrame({"month": _months("2000-01", 10),
                        "gap": [-0.1] * 5 + [-0.2, -0.25, 0.03, 0.05, -0.1]})
    sub = ph.gap_subtitle(gap, "Ordu", "Giresun")
    assert sub.startswith("Ordu's monthly price ran a median 10.0% below Giresun's over 10 months")
    assert "% below and " in sub and "% above" in sub
    gap2 = pd.DataFrame({"month": _months("2000-01", 4), "gap": [-0.1, -0.12, -0.05, -0.2]})
    assert "between" in ph.gap_subtitle(gap2, "Ordu", "Giresun")
    assert ph.gap_subtitle(gap2, "Ordu", "Giresun").endswith("below.")


def test_gap_subtitle_all_below_band_runs_from_small_to_large():
    gap = pd.DataFrame({"month": _months("2000-01", 11),
                        "gap": [-0.03, -0.05, -0.08, -0.1, -0.1, -0.1, -0.12, -0.14, -0.16,
                                -0.17, -0.3]})
    sub = ph.gap_subtitle(gap, "Ordu", "Giresun")
    lo, hi = gap["gap"].quantile(0.9), gap["gap"].quantile(0.1)  # smallest, largest discount
    assert sub.endswith(f"8 in 10 months fell between {abs(lo) * 100:.1f}% and "
                        f"{abs(hi) * 100:.1f}% below.")
    assert abs(lo) < abs(hi)


def test_gap_subtitle_all_above_band_runs_from_small_to_large():
    gap = pd.DataFrame({"month": _months("2000-01", 11),
                        "gap": [0.03, 0.05, 0.08, 0.1, 0.1, 0.1, 0.12, 0.14, 0.16, 0.17, 0.3]})
    sub = ph.gap_subtitle(gap, "Ordu", "Giresun")
    lo, hi = gap["gap"].quantile(0.1), gap["gap"].quantile(0.9)
    assert sub.startswith("Ordu's monthly price ran a median 10.0% above Giresun's")
    assert sub.endswith(f"8 in 10 months fell between {lo * 100:.1f}% and {hi * 100:.1f}% above.")


# --- crop and frost ---------------------------------------------------------------------

def _crop() -> pd.DataFrame:
    return pd.DataFrame({
        "year": [2001, 2002, 2003, 2004, 2005, 2006],
        "season": ["2001/02", "2002/03", "2003/04", "2004/05", "2005/06", "2006/07"],
        "crop_t": [100.0, 80.0, 120.0, 20.0, 110.0, 90.0],
        "season_avg_usd": [3.0, 3.2, 2.9, 6.0, 3.1, 3.3],
    })


def test_correlation_without_years_and_partial_season():
    df = _crop()
    note = ph.correlation_without_note(df, "crop_t", [2004], exclude_season="2006/07")
    expect = df[(df["year"] != 2004) & (df["season"] != "2006/07")]
    r = expect["crop_t"].corr(expect["season_avg_usd"])
    assert note == f"Without 2004, the correlation is {r:.2f} (4 seasons).".replace("-", "−")


def test_partial_season_found_from_prices():
    prices = pd.DataFrame({"month": ["2006-09"], "season": ["2006/07"]})
    assert ph.partial_season(_crop(), "crop_t", prices) == "2006/07"
    full = pd.DataFrame({"month": _months("2006-09", 12), "season": ["2006/07"] * 12})
    assert ph.partial_season(_crop(), "crop_t", full) is None
    assert ph.partial_season(_crop(), "crop_t", None) is None


def test_frost_crop_subtitle_and_smallest_note():
    df = pd.DataFrame({"year": [1, 2, 3, 4, 5], "frost_days": [1.0, 9.0, 2.0, 3.0, 2.5],
                       "crop_t": [100.0, 40.0, 90.0, 30.0, 95.0]})
    sub = ph.frost_crop_subtitle(df, "frost_days", "crop_t")
    r = df["frost_days"].corr(df["crop_t"])
    assert f"{r:.2f}".replace("-", "−") in sub and "Over 5 years" in sub
    few = df.head(2)
    assert ph.frost_crop_subtitle(few, "frost_days", "crop_t", "Giresun") == (
        "Spring frost days against the Giresun crop estimate.")
    assert ph.frost_crop_subtitle(few, "frost_days", "crop_t") == (
        "Spring frost days against the crop estimate.")
    note = ph.smallest_crops_note(df, "frost_days", "crop_t", n=2)
    assert note == "The two smallest crops, 4 and 2, followed 3.0 and 9.0 frost days."


@pytest.mark.parametrize("r, words", [
    (-0.6, "more frost days have usually meant smaller crops"),
    (-0.3, "more frost days have loosely gone with smaller crops"),
    (-0.1, "the frost-day count says little about the crop"),
    (0.3, "more frost days have not meant smaller crops"),
])
def test_frost_words(r, words):
    assert ph.frost_words(r) == words


def test_partial_year_note():
    built = datetime(2026, 4, 10, tzinfo=timezone.utc)
    assert ph.partial_year_note(2026, built.isoformat(), last_month=4) == (
        "2026 is partial: the data was built on 10 April 2026, before its frost window ended.")
    assert ph.partial_year_note(2026, "2026-11-17T14:19:25+00:00", last_month=4) is None
    assert ph.partial_year_note(2025, "2026-01-03T00:00:00+00:00", last_month=4) is None
    assert ph.partial_year_note(2026, None, last_month=4) is None


# --- tables -----------------------------------------------------------------------------

def _board():
    rows = []
    for m, r in {"naive": (1.0, 1.0), "sarima": (1.0426, 1.0188), "lightgbm": (1.054, 0.98)}.items():
        for h, v in zip((1, 3), r):
            rows.append((m, h, 24, 0.3 * v, v))
    return pd.DataFrame(rows, columns=["method", "horizon", "n", "mae", "ratio"])


def test_metric_table_html_groups_rows_and_highlight():
    html = ph.metric_table_html(
        _board(), [("Error vs naive", "ratio", ph.fmt_ratio(3))],
        caption="Test <caption>", order=["naive", "lightgbm", "sarima"],
    )
    assert 'data-quarto-disable-processing="true"' in html
    assert "Test &lt;caption&gt;" in html
    assert html.index("Naive") < html.index("LightGBM") < html.index("SARIMA")
    assert '<tr class="hl"><td>Naive</td>' in html
    assert ">1.043<" in html and ">0.980<" in html
    assert ">1 mo<" in html and ">3 mo<" in html
    # one group: no group header row
    assert "colspan" not in html


def test_metric_table_html_two_groups_have_a_spanning_header_and_na():
    df = _board()
    df.loc[(df["method"] == "sarima") & (df["horizon"] == 3), "mae"] = np.nan
    html = ph.metric_table_html(
        df, [("Ratio", "ratio", ph.fmt_ratio(2)), ("MAE", "mae", ph.fmt_usd)],
        caption="c", names={"naive": "Lira naive"}.get,
    )
    assert html.count('colspan="2"') == 2
    assert "Lira naive" in html
    assert "n/a" in html


def test_formatters():
    assert ph.fmt_ratio(3)(1.02205) == "1.022"
    assert ph.fmt_pct(0.8418) == "84%"
    assert ph.fmt_signed(-0.0954) == "−0.10"
    assert ph.fmt_signed(-0.0034) == "0.00"
    assert ph.fmt_signed(0.176) == "+0.18"
    assert ph.fmt_p(0.0114) == "0.01" and ph.fmt_p(0.0002) == "<0.001"
    assert ph.fmt_p(0.0095) == "0.01" and ph.fmt_p(0.004) == "0.004"
    assert ph.fmt_p(float("nan")) == "n/a"


# --- forecasting takeaways --------------------------------------------------------------

def test_dev_subtitle_names_no_method_and_gives_the_closest_margin():
    board = _board()
    board = board[~((board["method"] == "lightgbm") & (board["horizon"] == 3))]
    sub = ph.dev_subtitle(board)
    assert "None beat naive at any horizon" in sub
    assert "the closest lost by 2% to 4%" in sub
    assert "SARIMA" not in sub and "LightGBM" not in sub


def test_dev_subtitle_counts_scores_under_one_without_names():
    sub = ph.dev_subtitle(_board())
    assert "1 of 4 method-horizon scores came in under 1" in sub
    assert "LightGBM" not in sub


def _shocks():
    rows = []
    for m, mult, rcalm, rshock in [("naive", 2.0, 1.0, 1.0), ("sarima", 2.5, 1.05, 0.94),
                                   ("season_reg", 1.1, 3.0, 1.5)]:
        for h in (1, 6):
            calm = 0.2 * rcalm
            rows.append((m, h, "calm", calm, rcalm))
            rows.append((m, h, "shock", calm * mult, rshock))
    return pd.DataFrame(rows, columns=["method", "horizon", "period", "mae", "ratio"])


def test_shock_subtitle_error_multiple_and_under_one_count():
    sub = ph.shock_subtitle(_shocks(), exclude=("season_reg",))
    assert "2.0 to 2.5 times" in sub
    assert "2 of 4 shock-month scores came in under 1, by at most 6%" in sub
    assert "SARIMA" not in sub


def test_shock_table_is_wide_by_period():
    wide = ph.shock_table(_shocks())
    assert {"calm", "shock"} <= set(wide.columns)
    assert len(wide) == 6


def _holdout(lgb=(0.95, 1.2), sar=(1.05, 1.01)):
    rows = [("naive", 1, 24, 0.3, 1.0), ("naive", 6, 24, 1.3, 1.0)]
    for m, r in {"lightgbm": lgb, "sarima": sar}.items():
        rows += [(m, 1, 24, 0.3, r[0]), (m, 6, 24, 1.3, r[1])]
    return pd.DataFrame(rows, columns=["method", "horizon", "n", "mae", "ratio"])


def test_holdout_subtitle_no_names_when_no_method_wins_everywhere():
    sub = ph.holdout_subtitle(_holdout())
    assert sub == ("24 forecasts per horizon, scored once, never tuned on. No method beat naive "
                   "at every horizon; 1 of 4 scores came in under 1, each from a method that "
                   "lost at another horizon.")


def test_holdout_subtitle_names_an_every_horizon_winner_with_the_chance_caveat():
    sub = ph.holdout_subtitle(_holdout(lgb=(0.95, 0.9)))
    assert "LightGBM came in under naive at every horizon" in sub
    assert "could be chance" in sub


def test_holdout_dev_note_checks_the_same_horizon_in_development():
    dev = _board()  # lightgbm h1 1.054 in dev
    assert ph.holdout_dev_note(_holdout(), dev) == (
        "Each score that beat naive in the holdout had lost to naive at that same horizon in "
        "development, so these wins look like luck, not skill.")
    dev.loc[(dev["method"] == "lightgbm") & (dev["horizon"] == 1), "ratio"] = 0.99
    assert ph.holdout_dev_note(_holdout(), dev) == (
        "1 of the holdout scores under 1 was also under 1 in development at the same horizon.")


def test_holdout_dev_note_without_a_development_loss_makes_no_luck_claim():
    dev = _board()
    dev.loc[(dev["method"] == "lightgbm") & (dev["horizon"] == 1), "ratio"] = 1.0  # a tie, not a loss
    assert ph.holdout_dev_note(_holdout(), dev) == (
        "None of the holdout scores that beat naive also beat it in development at the same "
        "horizon.")


def test_forecast_3m_subtitle():
    f = pd.DataFrame({"target_month": ["2005-01", "2005-02"], "actual": [3.0, 3.0],
                      "naive": [3.4, 2.6], "best_other": [3.5, 2.55],
                      "best_other_method": ["sarima", "sarima"]})
    sub = ph.forecast_3m_subtitle(f, 3)
    assert sub == ("3 months ahead, naive missed by $0.40/kg on average; SARIMA, "
                   "the closest challenger, missed by 19% more.")


def test_band_subtitle_counts_held_and_shock_misses():
    band = pd.DataFrame({
        "target_month": ["2004-12", "2005-03", "2005-04", "2006-01", "2006-02"],
        "actual": [5.0, 9.0, 4.0, 1.0, 3.0],
        "q10": [4.0, 4.0, 4.0, 2.0, 2.0], "q90": [6.0, 6.0, 6.0, 4.0, 4.0],
    })
    sub = ph.band_subtitle(band, [("2005-01", "2005-12")], horizon=3)
    assert sub == ("3 months ahead, the 8-in-10 range held 60% of the time (3 of 5 months); "
                   "1 of the 2 misses fell in a shock period.")


def _check():
    rows = []
    for m, g, n in [("sarimax", (1.120, 1.016), (1.131, 1.014)),
                    ("lightgbm", (1.058, 1.108), (1.061, 1.137))]:
        for h, gv, nv in zip((1, 3), g, n):
            rows += [(m, h, "giresun", gv), (m, h, "national", nv)]
    return pd.DataFrame(rows, columns=["method", "horizon", "crop_source", "ratio"])


def _dev_for_check():
    rows = [("sarimax", 1, 1.122), ("sarimax", 3, 1.022), ("lightgbm", 1, 1.054),
            ("lightgbm", 3, 1.134), ("naive", 1, 1.0), ("naive", 3, 1.0)]
    return pd.DataFrame([(m, h, 10, 0.1, r) for m, h, r in rows],
                        columns=["method", "horizon", "n", "mae", "ratio"])


def test_crop_check_table_rows_on_time_and_late():
    t = ph.crop_check_table(_dev_for_check(), _check(), main_source="giresun")
    labels = list(dict.fromkeys(t["row"]))
    assert labels == ["SARIMAX, Giresun, on time", "SARIMAX, Giresun, a month late",
                      "SARIMAX, National, a month late", "LightGBM, Giresun, on time",
                      "LightGBM, Giresun, a month late", "LightGBM, National, a month late"]


def test_crop_check_subtitle_timing_and_national():
    sub = ph.crop_check_subtitle(_dev_for_check(), _check(), main_source="giresun",
                                 rule="the August rule")
    assert sub == ("Moving every crop estimate a month later changed the scores by at most "
                   "0.03, so the August rule shows no sign of a leak; at that month-late "
                   "timing the national estimate scored worse in 3 of 4 method-horizon pairs.")


def test_crop_check_subtitle_flags_a_large_shift():
    check = _check()
    check.loc[(check["crop_source"] == "giresun") & (check["horizon"] == 1)
              & (check["method"] == "sarimax"), "ratio"] = 1.30
    sub = ph.crop_check_subtitle(_dev_for_check(), check, main_source="giresun")
    assert "changed the scores by up to 0.18" in sub
    assert "no sign of a leak" not in sub and "may have gained from a leak" in sub
    assert "at that month-late timing" in sub


def _lira():
    rows = []
    for m in ("naive", "fx36", "infl"):
        for h in (1, 3, 6):
            for period, mape in (("all", 0.97), ("calm", 1.016), ("crisis", 0.613 + 0.1 * (6 - h) / 5)):
                v = 1.0 if m == "naive" else mape
                p = np.nan if m == "naive" else {1: 0.70, 3: 0.058, 6: 0.0115}[h]
                rows.append((m, h, period, v, v, p))
    return pd.DataFrame(rows, columns=["method", "horizon", "period", "mape_ratio", "mae_ratio",
                                       "dm_p"])


def test_lira_split_subtitle():
    sub = ph.lira_split_subtitle(_lira(), "fx36")
    # crisis ratios 0.713 / 0.673 / 0.613 -> 29% to 39% below; calm 1.016 -> within 2%
    assert sub == ("In the crisis months its error was 29% to 39% below naive's; "
                   "in calm months it was within 2% of naive's.")


def test_lira_p_note_uses_the_all_period_only():
    note = ph.lira_p_note(_lira(), {"fx36": "FX drift, 36 m"})
    assert note == "FX drift, 36 m: p = 0.70 / 0.06 / 0.01 at 1 / 3 / 6 months."


def test_wide_ratios_for_chart():
    wide = ph.lira_split(_lira(), "fx36", ("calm", "crisis"))
    assert list(wide.index) == [1, 3, 6] and list(wide.columns) == ["calm", "crisis"]
    assert math.isclose(wide.loc[6, "crisis"], 0.613)


def test_range_methods_have_readable_names():
    from hazelnut.site.labels import method_name

    assert method_name("naive_emp") == "Naive range (past moves)"
    assert method_name("naive_vol") == "Naive range, volatility-scaled"
    assert method_name("lightgbm_q") == "LightGBM quantiles"


def test_gap_detail_subtitle_counts_dearer_months_and_widest_gap():
    gap = pd.DataFrame({"month": ["2000-01", "2000-02", "2000-03", "2000-04"],
                        "gap": [-0.1, 0.02, -0.3, -0.05]})
    assert ph.gap_detail_subtitle(gap, "Ordu") == (
        "Ordu was dearer in 1 of 4 months; its widest discount was 30.0%, in March 2000.")


def test_split_outliers_and_note():
    gap = pd.DataFrame({"month": ["2007-06", "2008-01", "2024-01", "2025-09"],
                        "gap": [4.83, -0.1, 11.3, 0.23]})
    kept, dropped = ph.split_outliers(gap, limit=0.5)
    assert list(kept["month"]) == ["2008-01", "2025-09"]
    assert list(dropped["month"]) == ["2007-06", "2024-01"]
    assert ph.outlier_note(dropped, "Ordu", "Giresun", 0.5) == (
        "Left out: June 2007 and January 2024, when Ordu's average was more than 50% away "
        "from Giresun's (most likely entry errors in the source).")
    assert ph.outlier_note(dropped.iloc[0:0], "Ordu", "Giresun", 0.5) is None


def _ranges():
    rows = []
    for m, cov, skill in [("naive_emp", (0.82, 0.84), (0.0, 0.0)),
                          ("sarima", (0.87, 0.85), (-0.003, -0.03)),
                          ("lightgbm_q", (0.56, 0.5), (-0.1, -0.22))]:
        for h, c, s in zip((1, 3), cov, skill):
            rows.append((m, h, c, 0.7, c + 0.08, s))
    return pd.DataFrame(rows, columns=["method", "horizon", "cov80", "width80", "cov90", "skill"])


def test_ranges_subtitle_base_coverage_and_no_better_method():
    assert ph.ranges_subtitle(_ranges(), "naive_emp") == (
        "An honest 8-in-10 range holds about 80% of the time. Naive range (past moves) held 82% to "
        "84%, and no other method scored better at any horizon.")
    r = _ranges()
    r.loc[(r["method"] == "sarima") & (r["horizon"] == 1), "skill"] = 0.01
    assert "1 of 4 other scores beat it" in ph.ranges_subtitle(r, "naive_emp")


def test_ranges_order_base_first_then_by_skill():
    assert ph.ranges_order(_ranges(), "naive_emp") == ["naive_emp", "sarima", "lightgbm_q"]


def test_lira_subtitle_first_horizon_and_trend_gains():
    lira = _lira()
    lira.loc[(lira["period"] == "all") & (lira["horizon"] == 1) & (lira["method"] != "naive"),
             "mape_ratio"] = 1.01
    sub = ph.lira_subtitle(lira, ["fx36", "infl"], "the trend forecasts")
    assert sub == ("In percent terms nothing beat naive at 1 month; at 3 and 6 months the "
                   "trend forecasts had 3% lower error, which is suggestive only.")
    sub = ph.lira_subtitle(lira, ["fx36", "infl"], "the trend forecasts",
                           caveat="suggestive (6 variants tried)")
    assert sub.endswith("had 3% lower error, suggestive (6 variants tried).")


def test_periods_label():
    assert ph.periods_label([("2018-05", "2018-12"), ("2021-09", "2023-12")]) == (
        "May to December 2018 and September 2021 to December 2023")


def test_shock_multiple_and_band_held():
    lo, hi = ph.shock_multiple(_shocks(), exclude=("season_reg",))
    assert (round(lo, 2), round(hi, 2)) == (2.0, 2.5)
    band = pd.DataFrame({"target_month": ["2005-01", "2005-02"], "actual": [1.0, 5.0],
                         "q10": [0.5, 0.5], "q90": [2.0, 2.0]})
    assert ph.band_held(band) == (0.5, 1, 2)

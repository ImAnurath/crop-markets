"""Dashboard helpers in page_helpers: load-or-None, panel heads and computed takeaways."""
import pandas as pd
import pytest

from hazelnut.site import page_helpers as ph
from hazelnut.site.labels import METHODS, method_name


# --- loading ----------------------------------------------------------------------------

def test_read_csv_or_none_reads_a_good_file(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("x,y\n1,2\n", encoding="utf-8")
    df = ph.read_csv_or_none(f, required=("x", "y"))
    assert df is not None and df.to_dict("list") == {"x": [1], "y": [2]}


def test_read_csv_or_none_missing_file(tmp_path):
    assert ph.read_csv_or_none(tmp_path / "nope.csv") is None


@pytest.mark.parametrize("text", ["", "x,y\n", "\x00\x01garbage\n\"unclosed"])
def test_read_csv_or_none_empty_or_unreadable(tmp_path, text):
    f = tmp_path / "a.csv"
    f.write_text(text, encoding="utf-8")
    assert ph.read_csv_or_none(f, required=("x", "y")) is None


def test_read_csv_or_none_missing_required_column(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("x\n1\n", encoding="utf-8")
    assert ph.read_csv_or_none(f, required=("x", "y")) is None
    assert ph.read_csv_or_none(f) is not None


def test_read_csv_or_none_a_directory_is_unreadable(tmp_path):
    assert ph.read_csv_or_none(tmp_path) is None


def test_unavailable_html_has_the_exact_text():
    html = ph.unavailable_html()
    assert "This chart's data is not available in this refresh." in html
    assert 'class="chart-error"' in html


def test_panel_head_escapes_and_uses_h2():
    html = ph.panel_head_html("Price <b>", "A & B")
    assert '<h2 class="ptitle">Price &lt;b&gt;</h2>' in html
    assert '<div class="sub">A &amp; B</div>' in html


# --- method names -----------------------------------------------------------------------

def test_method_names_are_shared_with_the_workbook():
    from hazelnut.site import workbook

    assert workbook.method_name is method_name
    assert all(method_name(m) != m for m in METHODS)  # each has a readable name
    assert method_name("chronos") == "Chronos-Bolt"
    assert method_name("mystery") == "mystery"


# --- price history ----------------------------------------------------------------------

def _prices(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({"month": list(values), "usd_kg": list(values.values())})


def test_shock_move_is_low_before_peak_to_peak():
    p = _prices({"2013-12": 3.3, "2014-01": 3.0, "2014-02": 2.9, "2014-03": 5.0,
                 "2014-04": 7.5, "2014-05": 1.0, "2014-06": 6.0})
    move = ph.shock_move(p, "2014-01", "2014-06")
    # the low must come before the peak: 1.0 in May (after the peak) does not count
    assert (move.low_month, move.low, move.peak_month, move.peak) == ("2014-02", 2.9, "2014-04", 7.5)
    assert move.months == 2


def test_shock_move_with_no_prices_in_the_window_is_none():
    assert ph.shock_move(_prices({"2013-12": 3.3}), "2014-01", "2014-06") is None


def test_price_subtitle_is_computed_from_the_prices():
    p = _prices({"2014-01": 3.0, "2014-03": 2.9, "2015-05": 7.59,
                 "2025-01": 3.69, "2025-10": 7.56})
    sub = ph.price_subtitle(p, [("the 2014 frost", ("2014-01", "2015-12")),
                                ("the 2025 short crop", ("2025-01", "2025-12"))])
    assert sub == ("The 2014 frost took the price from $2.90 to $7.59 in 14 months; "
                   "the 2025 short crop, from $3.69 to $7.56 in 9 months.")


def test_price_subtitle_without_shock_data_falls_back():
    sub = ph.price_subtitle(_prices({"2020-01": 3.0}), [("the 2014 frost", ("2014-01", "2015-12"))])
    assert sub == "Monthly exchange price; shaded periods are supply shocks."


# --- range ------------------------------------------------------------------------------

RANGE = pd.DataFrame({
    "horizon": [1, 3, 6], "target_month": ["2026-10", "2026-12", "2027-03"],
    "q05": [3.7, 3.2, 2.8], "q10": [3.94, 3.45, 3.0651], "q50": [4.26, 4.33, 4.35],
    "q90": [4.78, 5.40, 6.049], "q95": [5.06, 5.81, 6.66],
    "from_month": ["2026-09"] * 3, "from_usd": [4.2824] * 3,
})


def test_range_subtitle_uses_the_longest_horizon():
    assert ph.range_subtitle(RANGE) == (
        "If past 6-month moves repeat, eight times in ten the March 2027 price "
        "lands between $3.07 and $6.05."
    )


def test_range_coverage_note():
    ranges = pd.DataFrame({"method": ["naive_emp", "naive_emp", "sarima"], "horizon": [1, 6, 6],
                           "cov80": [0.81, 0.8312, 0.5]})
    assert ph.range_coverage_note(ranges, "naive_emp", 6) == (
        "In testing, the 8-in-10 band held 83% of the time at 6 months."
    )
    assert ph.range_coverage_note(ranges, "naive_emp", 3) is None
    assert ph.range_coverage_note(None, "naive_emp", 6) is None


def test_range_label_from_crops_yml_currencies():
    assert ph.range_currencies_label(("usd",)) == "USD"
    assert ph.range_currencies_label(("usd", "eur")) == "USD, EUR"


# --- exports ----------------------------------------------------------------------------

TOP = pd.DataFrame({"partner": ["Italy", "Germany", "France", "Other"],
                    "net_kg": [3e7, 2.5e7, 8e6, 1.9e7], "fob_usd": [1, 1, 1, 1],
                    "share": [0.2853, 0.2246, 0.0735, 0.1694]})


def test_exports_subtitle_names_the_top_partners_and_their_share():
    assert ph.exports_subtitle(TOP, "December 2025") == (
        "Italy and Germany took 51% of export volume in the 12 months to December 2025."
    )
    assert ph.exports_subtitle(TOP, "December 2025", n=3).startswith(
        "Italy, Germany and France took 58%")


def test_exports_subtitle_ignores_other_even_when_large():
    top = TOP.assign(share=[0.1, 0.05, 0.02, 0.83])
    assert ph.exports_subtitle(top, "December 2025", n=1).startswith("Italy took 10%")


# --- crop vs price ----------------------------------------------------------------------

def test_season_progress():
    p = pd.DataFrame({"month": ["2026-08", "2026-09", "2026-10"],
                      "season": ["2025/26", "2026/27", "2026/27"], "usd_kg": [1, 2, 3]})
    assert ph.season_months(p, "2026/27") == ["2026-09", "2026-10"]
    assert ph.season_to_date_note(p, "2026/27") == (
        "2026/27 is season to date (September to October 2026), so its average is provisional."
    )
    one = p.iloc[:2]
    assert ph.season_to_date_note(one, "2026/27") == (
        "2026/27 is season to date (September 2026 only), so its average is provisional."
    )
    full = pd.DataFrame({"month": pd.period_range("2025-09", "2026-08", freq="M").astype(str),
                         "season": "2025/26", "usd_kg": 1.0})
    assert ph.season_to_date_note(full, "2025/26") is None


CROP = pd.DataFrame({
    "year": [2020, 2021, 2022, 2023, 2024],
    "season": ["2020/21", "2021/22", "2022/23", "2023/24", "2024/25"],
    "crop_t": [100.0, 200.0, 300.0, None, 400.0],
    "season_avg_usd": [5.0, 4.0, 3.5, 3.0, 9.0],
})


def test_crop_price_subtitle_excludes_the_partial_season():
    # complete rows 2020, 2021, 2022 (2023 lacks the crop; 2024/25 is excluded as partial)
    sub = ph.crop_price_subtitle(CROP, "crop_t", exclude_season="2024/25")
    assert sub.startswith("Over 3 seasons, bigger crops have usually come with lower prices")
    assert "(correlation −0.98)" in sub


@pytest.mark.parametrize("r, words", [
    (-0.6, "bigger crops have usually come with lower prices"),
    (-0.3, "bigger crops have loosely gone with lower prices"),
    (0.05, "crop size alone says little about the price"),
    (0.5, "bigger crops have not come with lower prices"),
])
def test_correlation_words(r, words):
    assert ph.correlation_words(r) == words


def test_crop_price_subtitle_too_few_seasons():
    assert ph.crop_price_subtitle(CROP.iloc[:2], "crop_t") == (
        "Crop estimate against the season's average price."
    )


# --- scoreboard -------------------------------------------------------------------------

def _board(ratios: dict[str, list[float]], n=(236, 234, 231)) -> pd.DataFrame:
    rows = []
    for m, rs in ratios.items():
        for h, r, k in zip((1, 3, 6), rs, n):
            rows.append({"method": m, "horizon": h, "n": k, "mae": r * 0.3, "ratio": r})
    return pd.DataFrame(rows)


DEV = _board({"chronos": [1.08, 1.07, 1.06], "naive": [1.0, 1.0, 1.0],
              "sarima": [1.04, 1.02, 1.04], "season_reg": [3.16, 1.63, 1.09]})


def test_scoreboard_rows_put_naive_first_then_by_mean_ratio():
    rows = ph.scoreboard_rows(DEV)
    assert [r[0] for r in rows] == ["naive", "sarima", "chronos", "season_reg"]
    assert rows[1][1] == "SARIMA" and rows[1][2] == {1: 1.04, 3: 1.02, 6: 1.04}


def test_scoreboard_subtitle_when_nothing_beats_naive():
    assert ph.scoreboard_subtitle(DEV) == (
        "Each method's error divided by naive's (the price stays where it is): above 1 is "
        "worse. None beat naive at any horizon."
    )


def test_scoreboard_subtitle_does_not_crown_a_winner():
    dev = _board({"naive": [1, 1, 1], "sarima": [0.98, 1.02, 1.04]})
    sub = ph.scoreboard_subtitle(dev)
    assert "1 of 3 method-horizon scores came in under 1" in sub
    assert "win" not in sub.lower() and "best" not in sub.lower()


def test_scoreboard_html_table_naive_amber_and_footnote():
    hold = _board({"chronos": [1.15, 0.998, 0.99], "naive": [1, 1, 1],
                   "sarima": [0.95, 1.02, 1.01]}, n=(24, 24, 24))
    html = ph.scoreboard_html(DEV, hold, "analyses/forecasting.qmd")
    assert html.count("<tr") == 1 + 4
    assert 'data-quarto-disable-processing="true"' in html  # keep Quarto off the table
    assert '<tr class="hl"><td>Naive</td>' in html
    assert '<th class="n" scope="col">1 mo</th>' in html and ">6 mo</th>" in html
    assert '<td class="n">3.16</td>' in html
    assert "over 231 to 236 forecasts per horizon" in html
    assert "scored once, never tuned on" in html
    assert "no method beat naive at every horizon" in html
    assert 'href="analyses/forecasting.qmd"' in html


def test_scoreboard_html_without_holdout_still_links_the_analysis():
    html = ph.scoreboard_html(DEV, None, "analyses/forecasting.qmd")
    assert "holdout" not in html.lower()
    assert 'href="analyses/forecasting.qmd"' in html


def test_scoreboard_holdout_names_methods_under_naive_everywhere():
    hold = _board({"naive": [1, 1, 1], "sarima": [0.9, 0.95, 0.99]}, n=(24, 24, 24))
    html = ph.scoreboard_html(DEV, hold, "x.qmd")
    assert "SARIMA came in under naive at every horizon" in html


def test_read_json_or_none(tmp_path):
    f = tmp_path / "m.json"
    f.write_text('{"as_of": "2026-09"}', encoding="utf-8")
    assert ph.read_json_or_none(f) == {"as_of": "2026-09"}
    assert ph.read_json_or_none(tmp_path / "nope.json") is None
    f.write_text("{not json", encoding="utf-8")
    assert ph.read_json_or_none(f) is None


def test_shock_years_label():
    shocks = [("2005-01", "2005-12"), ("2014-01", "2015-12"), ("2025-01", "2025-12")]
    assert ph.shock_years_label(shocks) == "2005, 2014-15 and 2025"
    assert ph.shock_years_label([("1999-06", "2001-02")]) == "1999-2001"


def test_crop_panel_labels_the_season_to_date():
    prices = pd.DataFrame({"month": ["2024-09", "2024-10"], "season": ["2024/25"] * 2,
                           "usd_kg": [9.0, 9.0]})
    chart_df, sub, note = ph.crop_panel(CROP, "crop_t", prices)
    assert chart_df["season"].iloc[-1] == "2024/25 to date"
    assert list(CROP["season"])[-1] == "2024/25"  # the input is not changed
    assert note.startswith("2024/25 is season to date (September to October 2024)")
    assert sub.startswith("Over 3 seasons,")  # the partial season is left out of the r


def test_crop_panel_complete_latest_season_is_kept():
    _, sub, note = ph.crop_panel(CROP, "crop_t", None)
    assert note is None
    assert sub.startswith("Over 4 seasons,")


def test_scoreboard_html_links_method_names_to_their_methods_cards():
    html = ph.scoreboard_html(DEV, None, "x.qmd", methods_href="../methods.qmd")
    assert '<a href="../methods.qmd#naive">Naive</a>' in html
    assert "methods.qmd" not in ph.scoreboard_html(DEV, None, "x.qmd")


# --- Turkish ----------------------------------------------------------------------------

def test_price_subtitle_in_turkish_raises_a_dotted_i(turkish):
    p = _prices({"2014-01": 3.0, "2015-05": 7.59})
    assert ph.price_subtitle(p, [("ilk don", ("2014-01", "2015-12"))]) == (
        "İlk don, fiyatı 16 ay içinde 3,00 $ seviyesinden 7,59 $ seviyesine çıkardı.")


def test_exports_subtitle_in_turkish_names_destinations_in_turkish(turkish):
    assert ph.exports_subtitle(TOP, "Aralık 2025") == (
        "İtalya ve Almanya, Aralık 2025 ile biten 12 ayda ihracat hacminden %51 pay aldı."
    )

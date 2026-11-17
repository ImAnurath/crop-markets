import numpy as np
import pandas as pd
import pytest

from hazelnut.site.results import build_results

MONTHS = pd.period_range("2017-01", "2019-12", freq="M")  # spans the 2018 lira crisis


def _point(method: str, scale: float, horizons=(1, 3)) -> pd.DataFrame:
    rows = []
    for i, origin in enumerate(MONTHS[:-3]):
        for h in horizons:
            actual = 3.0 + 0.05 * ((i + h) % 7)
            rows.append((method, str(origin), h, str(origin + h),
                         actual + scale * (1 + (i % 3)), actual, False))
    return pd.DataFrame(rows, columns=["method", "origin", "horizon", "target_month",
                                       "forecast", "actual", "fallback"])


def _quant(method: str) -> pd.DataFrame:
    r = _point(method, 0.1).drop(columns="forecast")
    c = r["actual"]
    for q, d in (("q05", -1.0), ("q10", -0.6), ("q50", 0.0), ("q90", 0.6), ("q95", 1.0)):
        r[q] = c + d + 0.05
    return r


def _write(folder, df):
    folder.mkdir(parents=True, exist_ok=True)
    df.to_csv(folder / f"{df['method'].iloc[0]}.csv", index=False)


@pytest.fixture
def bt(tmp_path):
    root = tmp_path / "bt"
    for f in ("dev", "holdout", "dev_try"):
        for m, s in (("naive", 0.3), ("sarima", 0.2)):
            _write(root / f, _point(m, s))
    for m, s in (("naive", 0.3), ("lightgbm", 0.2), ("lightgbm_nat", 0.25)):
        _write(root / "dev_late", _point(m, s))
    for m in ("naive_emp", "sarima"):
        _write(root / "dev_ranges", _quant(m))
    return root


def test_scoreboard_ratio_is_one_for_naive(bt, tmp_path):
    out = tmp_path / "out"
    build_results(bt, out)
    s = pd.read_csv(out / "scoreboard_dev.csv")
    assert list(s.columns) == ["method", "horizon", "n", "mae", "ratio"]
    assert (s[s.method == "naive"]["ratio"] == 1.0).all()
    assert (s[s.method == "sarima"]["ratio"] < 1.0).all()


def test_holdout_rows_carry_note(bt, tmp_path):
    out = tmp_path / "out"
    build_results(bt, out)
    h = pd.read_csv(out / "scoreboard_holdout.csv")
    assert (h["note"] == "scored once, never tuned on").all()
    assert "note" not in pd.read_csv(out / "scoreboard_dev.csv").columns


def test_missing_folder_is_skipped_not_fatal(bt, tmp_path):
    import shutil
    shutil.rmtree(bt / "dev_late")
    out = tmp_path / "out"
    written = build_results(bt, out)
    assert not (out / "crop_check.csv").exists()
    assert "crop_check.csv" not in written
    assert "scoreboard_dev.csv" in written
    assert build_results(tmp_path / "nothing", tmp_path / "o2") == []


def test_lira_has_all_calm_crisis_periods(bt, tmp_path):
    out = tmp_path / "out"
    build_results(bt, out)
    lira = pd.read_csv(out / "lira.csv")
    assert list(lira.columns) == ["method", "horizon", "period", "mape_ratio", "mae_ratio", "dm_p"]
    assert set(lira["period"]) == {"all", "calm", "crisis"}
    assert lira[(lira.method == "sarima") & (lira.period == "all")]["dm_p"].notna().all()


def test_other_tables(bt, tmp_path):
    out = tmp_path / "out"
    build_results(bt, out)
    assert set(pd.read_csv(out / "scoreboard_shocks.csv")["period"]) <= {"calm", "shock"}
    r = pd.read_csv(out / "ranges.csv")
    assert list(r.columns) == ["method", "horizon", "cov80", "width80", "cov90", "width90", "skill"]
    c = pd.read_csv(out / "crop_check.csv")
    assert set(c["crop_source"]) == {"giresun", "national"}
    f = pd.read_csv(out / "forecast_3m.csv")
    assert list(f.columns) == ["target_month", "actual", "naive", "best_other", "best_other_method"]
    assert (f["best_other_method"] == "sarima").all()
    b = pd.read_csv(out / "range_band_3m.csv")
    assert list(b.columns) == ["target_month", "actual", "q10", "q90"]
    assert len(b) == len(f)


def test_lira_dm_p_uses_log_errors(bt, tmp_path):
    from hazelnut.forecast.metrics import diebold_mariano

    out = tmp_path / "out"
    build_results(bt, out)
    d = pd.read_csv(out / "lira.csv")
    got = d[(d.method == "sarima") & (d.period == "all") & (d.horizon == 3)]["dm_p"].iloc[0]
    r = pd.read_csv(bt / "dev_try" / "sarima.csv").query("horizon == 3").sort_values("origin")
    n = pd.read_csv(bt / "dev_try" / "naive.csv").query("horizon == 3").sort_values("origin")
    la = np.abs(np.log(r["forecast"] / r["actual"])).to_numpy()
    lb = np.abs(np.log(n["forecast"] / n["actual"])).to_numpy()
    assert got == pytest.approx(diebold_mariano(la, lb, 3)[1])

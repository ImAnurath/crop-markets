import numpy as np
import pandas as pd
import pytest

from hazelnut.forecast.intervals import LEVELS, run_quantile_backtest
from hazelnut.forecast.methods import QUANTILE_REGISTRY
from hazelnut.forecast.methods import sarimax as sarimax_module
from hazelnut.forecast.methods.baselines import EmpiricalNaive
from hazelnut.forecast.methods.chronos import extend_tails
from hazelnut.forecast.metrics import interval_score, pinball, score_quantiles

M = lambda s: pd.Period(s, "M")  # noqa: E731


def random_walk(start="1995-01", end="2006-12", seed=0):
    idx = pd.period_range(start, end, freq="M")
    rng = np.random.default_rng(seed)
    price = pd.Series(np.exp(1 + np.cumsum(rng.normal(0, 0.05, len(idx)))), index=idx)
    return price, pd.DataFrame(index=idx)


# ---- metrics ---------------------------------------------------------------------------------

def test_pinball_loss():
    assert pinball(10.0, 8.0, 0.9) == pytest.approx(0.9 * 2)  # actual above: tau * miss
    assert pinball(10.0, 12.0, 0.9) == pytest.approx(0.1 * 2)  # actual below: (1 - tau) * miss
    assert pinball(5.0, 5.0, 0.1) == 0


def test_interval_score():
    assert interval_score(5.0, 4.0, 6.0, 0.2) == pytest.approx(2.0)  # inside: just the width
    assert interval_score(7.0, 4.0, 6.0, 0.2) == pytest.approx(2.0 + 10 * 1.0)
    assert interval_score(3.5, 4.0, 6.0, 0.1) == pytest.approx(2.0 + 20 * 0.5)


def test_score_quantiles_coverage_width_and_skill():
    cols = ["method", "origin", "horizon", "target_month", "actual", "fallback",
            "q05", "q10", "q50", "q90", "q95"]
    rows = [
        ("naive_emp", M("2010-01"), 1, M("2010-02"), 5.0, False, 3.0, 4.0, 5.0, 6.0, 7.0),
        ("naive_emp", M("2010-02"), 1, M("2010-03"), 6.5, False, 3.0, 4.0, 5.0, 6.0, 7.0),
        ("other", M("2010-01"), 1, M("2010-02"), 5.0, True, 4.0, 4.5, 5.0, 5.5, 6.0),
        ("other", M("2010-02"), 1, M("2010-03"), 6.5, False, 4.0, 4.5, 5.0, 5.5, 6.0),
    ]
    s = score_quantiles(pd.DataFrame(rows, columns=cols))
    base, other = s.loc[("naive_emp", 1)], s.loc[("other", 1)]
    assert base["cov80"] == pytest.approx(0.5) and base["cov90"] == pytest.approx(1.0)
    assert base["width80"] == pytest.approx(2.0) and other["width90"] == pytest.approx(2.0)
    assert other["cov90"] == pytest.approx(0.5) and other["fallback_share"] == pytest.approx(0.5)
    assert base["skill"] == pytest.approx(0.0)
    expected = np.mean([pinball([5.0, 6.5], q, lv) for q, lv in
                        zip((4.0, 4.5, 5.0, 5.5, 6.0), LEVELS)])
    assert other["pinball"] == pytest.approx(expected)


# ---- empirical-quantile baselines ------------------------------------------------------------

def test_empirical_quantiles_match_past_changes():
    price, inputs = random_walk(end="2004-12")
    out = EmpiricalNaive().quantiles(price, inputs, [3], LEVELS)
    log_p = np.log(price.to_numpy())
    changes = log_p[3:] - log_p[:-3]  # every 3-month change that ends by the origin
    assert out[3] == pytest.approx(list(price.iloc[-1] * np.exp(np.quantile(changes, LEVELS))))


@pytest.mark.parametrize("vol_window", [None, 12])
def test_empirical_ranges_use_nothing_after_origin(vol_window):
    price, inputs = random_walk()
    changed = price.copy()
    changed.loc[M("2006-01"):] *= np.exp(np.linspace(0.5, -1.0, 12))  # rewrite the last year
    method = EmpiricalNaive(vol_window=vol_window)
    a = run_quantile_backtest(method, price, inputs, first_origin=M("2005-01"))
    b = run_quantile_backtest(method, changed, inputs, first_origin=M("2005-01"))
    q = ["q05", "q10", "q50", "q90", "q95"]
    before = a["origin"] <= M("2005-12")
    assert before.sum() > 0
    pd.testing.assert_frame_equal(a.loc[before, q], b.loc[before, q])
    assert not np.allclose(a.loc[~before, q], b.loc[~before, q])
    assert not a["fallback"].any()


def test_vol_scaled_range_widens_after_turbulence():
    price, inputs = random_walk(end="2004-12")
    calm = EmpiricalNaive(vol_window=12).quantiles(price, inputs, [1], LEVELS)[1]
    wild = price.copy()
    wild.iloc[-6:] *= np.exp([0.3, -0.3, 0.3, -0.3, 0.3, -0.3])
    turbulent = EmpiricalNaive(vol_window=12).quantiles(wild, inputs, [1], LEVELS)[1]
    assert turbulent[-1] / turbulent[0] > calm[-1] / calm[0]


# ---- harness ---------------------------------------------------------------------------------

class Broken:
    name = "broken"

    def quantiles(self, history, inputs, horizons, levels):
        if 6 in horizons:
            raise RuntimeError("no convergence")
        return {h: [5.0, 1.0, 3.0, 4.0, 2.0] if h == 1 else None for h in horizons}


def test_quantile_backtest_sorts_and_falls_back():
    price, inputs = random_walk()
    res = run_quantile_backtest(Broken(), price, inputs, first_origin=M("2005-01"))
    assert list(res.columns) == ["method", "origin", "horizon", "target_month", "actual",
                                 "fallback", "q05", "q10", "q50", "q90", "q95"]
    first = res[res["origin"] == M("2005-01")].set_index("horizon")
    assert list(first.loc[1, ["q05", "q10", "q50", "q90", "q95"]]) == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert not first.loc[1, "fallback"] and first.loc[3, "fallback"] and first.loc[6, "fallback"]
    backup = EmpiricalNaive().quantiles(price.loc[:"2005-01"], inputs, [6], LEVELS)[6]
    assert list(first.loc[6, ["q05", "q10", "q50", "q90", "q95"]]) == pytest.approx(backup)
    assert (res["target_month"] == res["origin"] + res["horizon"]).all()


# ---- model-based ranges ----------------------------------------------------------------------

def test_sarima_quantiles_are_ordered_around_the_point_forecast(monkeypatch):
    monkeypatch.setattr(sarimax_module, "select_order", lambda y, x: ((0, 1, 0), (0, 0, 0, 12)))
    price, inputs = random_walk(end="2004-12")
    m = sarimax_module.Sarimax(exog=False)
    q = m.quantiles(price, inputs, [1, 6], LEVELS)
    point = m.forecast(price, inputs, [1, 6])
    for h in (1, 6):
        assert q[h] == sorted(q[h]) and q[h][2] == pytest.approx(point[h])
    assert q[6][-1] - q[6][0] > q[1][-1] - q[1][0]  # wider further ahead


def test_chronos_tails_extrapolated_in_log_space():
    native = {0.1: 4.0, 0.5: 5.0, 0.9: 6.0}
    out = extend_tails(native, LEVELS)
    assert out[1:4] == [4.0, 5.0, 6.0]
    assert out[0] < 4.0 and out[4] > 6.0
    ratio = 1.6448536 / 1.2815516
    assert np.log(out[4] / 5.0) == pytest.approx(np.log(6.0 / 5.0) * ratio)


def test_quantile_registry():
    assert {"naive_emp", "naive_vol", "sarima", "chronos", "lightgbm_q"} <= set(QUANTILE_REGISTRY)
    for name in ("naive_emp", "naive_vol", "lightgbm_q"):
        assert QUANTILE_REGISTRY[name]().name == name

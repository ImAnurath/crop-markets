"""Lira target: construction (old-lira rescaling), timing of the FX inputs, and no lookahead
in the drift / composed rules."""

import numpy as np
import pandas as pd
import pytest

from hazelnut.forecast.backtest import run_backtest
from hazelnut.forecast.dataset import (
    DATA_DIR,
    fx_eom_feature,
    load_dataset,
    load_dataset_try,
    target_series_try,
)
from hazelnut.forecast.methods import TRY_REGISTRY
from hazelnut.forecast.methods.baselines import Naive
from hazelnut.forecast.methods.lira import Composed, TryDrift, trailing_drift
from hazelnut.forecast.metrics import diebold_mariano, is_lira_crisis, score_relative

M = lambda s: pd.Period(s, "M")  # noqa: E731
HAS_DATA = (DATA_DIR / "giresun_monthly_price.csv").exists()


def test_try_target_rescales_old_lira():
    price = pd.DataFrame({
        "year": [1994, 2004, 2005], "month": [12, 12, 1],
        "price_avg_try": [9.0, 5_367_485.0, 5.56],
        "old_lira": [True, True, False],
    })
    t = target_series_try(price)
    assert t.name == "price_try"
    assert t.index[0] == M("1995-01")  # starts at TARGET_START, as the USD target does
    assert t.loc[M("2004-12")] == pytest.approx(5.367485)
    assert t.loc[M("2005-01")] == 5.56
    assert t.loc[M("2004-11")] != t.loc[M("2004-11")]  # absent month stays NaN


def test_fx_eom_takes_last_quote_of_the_month_only():
    fx = pd.DataFrame({
        "date": ["2018-08-30", "2018-08-31", "2018-09-03", "2018-07-31"],
        "usd_try": [6.5, 6.6, 6.9, 4.9],
    })
    f = fx_eom_feature(fx, pd.period_range("2018-07", "2018-10", freq="M"))
    assert f.name == "usd_try_eom"
    assert f.loc[M("2018-07")] == 4.9
    assert f.loc[M("2018-08")] == 6.6  # a September quote must not leak into August
    assert np.isnan(f.loc[M("2018-10")])


def test_trailing_drift():
    idx = pd.period_range("2020-01", "2020-04", freq="M")
    s = pd.Series([1.0, 2.0, 4.0, 8.0], index=idx)
    assert trailing_drift(s, 3) == pytest.approx(np.log(2))
    assert trailing_drift(s, 4) is None  # not enough history


def _toy(n=120, seed=0):
    idx = pd.period_range("2010-01", periods=n, freq="M")
    rng = np.random.default_rng(seed)
    fx = pd.Series(np.exp(np.cumsum(rng.normal(0.02, 0.03, n))), index=idx)
    usd = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.05, n))) * 3, index=idx)
    inputs = pd.DataFrame({
        "usd_try": fx,
        "usd_try_eom": fx * np.exp(rng.normal(0, 0.01, n)),
        "cpi": np.exp(np.cumsum(rng.normal(0.015, 0.002, n))),
        "crop_change": rng.normal(0, 0.2, n),
        "frost_days": rng.uniform(0, 5, n),
        "exports_kg": rng.uniform(1e6, 2e6, n),
        "volume_kg": rng.uniform(1e5, 2e5, n),
    }, index=idx)
    return usd * fx, inputs


def test_composed_with_fx_naive_is_lira_naive():
    price, inputs = _toy()
    out = Composed("naive").forecast(price, inputs, [1, 3, 6])
    assert out == pytest.approx(Naive().forecast(price, inputs, [1, 3, 6]))


def test_composed_fx_drift_formula():
    price, inputs = _toy()
    d = np.log(inputs["usd_try"].iloc[-1] / inputs["usd_try"].iloc[-13]) / 12
    out = Composed("drift", 12).forecast(price, inputs, [3])
    assert out[3] == pytest.approx(price.iloc[-1] * np.exp(3 * d))


@pytest.mark.parametrize("name", [n for n in TRY_REGISTRY if not n.startswith("try_sarima")])
def test_no_lookahead(name):
    """Changing everything after the origin must not change any forecast made at the origin."""
    price, inputs = _toy()
    origin = M("2016-06")
    a = TRY_REGISTRY[name]().forecast(price.loc[:origin], inputs.loc[:origin], [1, 3, 6])
    price2, inputs2 = price.copy(), inputs.copy()
    price2.loc[origin + 1:] *= 50
    inputs2.loc[origin + 1:] *= 50
    b = TRY_REGISTRY[name]().forecast(price2.loc[:origin], inputs2.loc[:origin], [1, 3, 6])
    assert all(v is not None for v in a.values())
    assert a == pytest.approx(b)
    # The rule methods also ignore rows past the origin if handed a longer inputs frame.
    if name.startswith(("composed", "try_drift")):
        c = TRY_REGISTRY[name]().forecast(price.loc[:origin], inputs2, [1, 3, 6])
        assert a == pytest.approx(c)


def test_try_drift_through_backtest_uses_only_past_prices():
    price, inputs = _toy()
    r = run_backtest(TryDrift(12), price, inputs, first_origin=M("2012-01"), horizons=[3])
    row = r[r["origin"] == M("2013-01")].iloc[0]
    expected = price[M("2013-01")] * (price[M("2013-01")] / price[M("2012-01")]) ** (3 / 12)
    assert row["forecast"] == pytest.approx(expected)
    assert not r["fallback"].any()


def test_score_relative_and_crisis_split():
    cols = ["method", "origin", "horizon", "target_month", "forecast", "actual", "fallback"]
    r = pd.DataFrame([
        ("naive", M("2010-01"), 1, M("2010-02"), 1.0, 2.0, False),
        ("naive", M("2018-07"), 1, M("2018-08"), 10.0, 20.0, False),
        ("other", M("2010-01"), 1, M("2010-02"), 1.5, 2.0, False),
        ("other", M("2018-07"), 1, M("2018-08"), 20.0, 20.0, False),
    ], columns=cols)
    s = score_relative(r)
    assert s.loc[("other", 1), "mae_ratio"] == pytest.approx(0.5 / 11)
    assert s.loc[("other", 1), "mape_ratio"] == pytest.approx(12.5 / 50)
    assert s.loc[("naive", 1), "log_mae"] == pytest.approx(np.log(2))
    split = score_relative(r, by="crisis")
    assert split.loc[("other", 1, "calm"), "mape_ratio"] == pytest.approx(0.5)
    assert split.loc[("other", 1, "crisis"), "mape_ratio"] == pytest.approx(0.0)
    assert is_lira_crisis(M("2022-06")) and not is_lira_crisis(M("2020-01"))


def test_diebold_mariano_sign():
    rng = np.random.default_rng(1)
    a = rng.uniform(0, 1, 300)
    stat, p = diebold_mariano(a, a + 0.5, h=3)
    assert stat < 0 and p < 1e-6


@pytest.mark.skipif(not HAS_DATA, reason="data/interim not built")
def test_real_try_target_matches_usd_times_fx():
    t_try, inputs = load_dataset_try()
    t_usd, _ = load_dataset()
    assert t_try.index.equals(t_usd.index) and not t_try.isna().any()
    ratio = t_try / (t_usd * inputs["usd_try"])
    assert ratio.between(0.999, 1.001).all()  # old-lira rescaling consistent across 2004/2005
    jump = np.log(t_try[M("2005-01")] / t_try[M("2004-12")])
    assert abs(jump) < 0.2
    assert inputs.loc[M("2010-01"):, "usd_try_eom"].notna().all()

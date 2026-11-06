import numpy as np
import pandas as pd

from hazelnut.forecast.backtest import holdout_start, run_backtest, split_dev

M = lambda s: pd.Period(s, "M")  # noqa: E731


def make_data(start="2004-07", end="2005-12", nan_at=()):
    idx = pd.period_range(start, end, freq="M")
    target = pd.Series(np.arange(1.0, len(idx) + 1), index=idx, name="price_usd")
    for m in nan_at:
        target[M(m)] = np.nan
    inputs = pd.DataFrame({"x": np.arange(len(idx), dtype=float)}, index=idx)
    return target, inputs


class Recorder:
    name = "recorder"

    def __init__(self):
        self.calls = []

    def forecast(self, history, inputs, horizons):
        self.calls.append((history.index[-1], inputs.index[-1]))
        return {h: 1.0 for h in horizons}


def test_method_sees_nothing_after_origin():
    target, inputs = make_data()
    rec = Recorder()
    res = run_backtest(rec, target, inputs, first_origin=M("2005-01"))
    assert rec.calls
    origins = sorted(set(res["origin"]))
    assert [c[0] for c in rec.calls] == origins
    assert all(h == i for h, i in rec.calls)
    assert origins[0] == M("2005-01") and origins[-1] == M("2005-11")


def test_rows_beyond_data_and_missing_actuals_dropped():
    target, inputs = make_data(nan_at=["2005-04"])
    res = run_backtest(Recorder(), target, inputs, first_origin=M("2005-01"))
    assert list(res.columns) == ["method", "origin", "horizon", "target_month", "forecast", "actual", "fallback"]
    assert (res["target_month"] <= M("2005-12")).all()
    assert not (res["target_month"] == M("2005-04")).any()
    assert (res["target_month"] == res["origin"] + res["horizon"]).all()
    assert res["actual"].notna().all()


class Flaky:
    name = "flaky"

    def forecast(self, history, inputs, horizons):
        if 3 in horizons:
            raise RuntimeError("no convergence")
        return {h: (None if h == 6 else 5.0) for h in horizons}


def test_failure_falls_back_to_last_valid_price():
    target, inputs = make_data(start="2004-01", end="2005-12")
    target[M("2004-12")] = 2.0
    target[M("2005-01")] = np.nan  # history ends with [2.0, NaN] at origin 2005-01
    res = run_backtest(Flaky(), target, inputs, first_origin=M("2005-01"))
    first = res[res["origin"] == M("2005-01")].set_index("horizon")
    assert first.loc[3, "forecast"] == 2.0 and first.loc[3, "fallback"]
    assert first.loc[6, "forecast"] == 2.0 and first.loc[6, "fallback"]
    assert first.loc[1, "forecast"] == 5.0 and not first.loc[1, "fallback"]


def test_score_from_filters_target_months():
    target, inputs = make_data()
    res = run_backtest(Recorder(), target, inputs, first_origin=M("2005-01"), score_from=M("2005-06"))
    assert len(res) > 0
    assert (res["target_month"] >= M("2005-06")).all()


def test_split_dev_drops_last_24_months():
    target, inputs = make_data(start="2000-01", end="2009-12")
    dev_t, dev_i = split_dev(target, inputs)
    assert len(dev_t) == len(target) - 24
    assert dev_t.index[-1] == M("2007-12")
    assert dev_i.index.equals(dev_t.index)
    assert holdout_start(target) == M("2008-01")

import numpy as np
import pandas as pd

from hazelnut.forecast.methods import REGISTRY
from hazelnut.forecast.methods import sarimax as sarimax_module
from hazelnut.forecast.methods.sarimax import Sarimax


def synthetic(start="1995-01", years=15, seed=0):
    idx = pd.period_range(start, periods=12 * years, freq="M")
    rng = np.random.default_rng(seed)
    t = np.arange(len(idx))
    season = 0.03 * np.sin(2 * np.pi * idx.month.to_numpy() / 12)
    price = pd.Series(np.exp(0.5 + 0.01 * t + season + rng.normal(0, 0.002, len(t))), index=idx)
    inputs = pd.DataFrame(
        {"crop_change": rng.normal(0, 0.2, len(t)), "usd_try": np.exp(0.02 * t)}, index=idx
    )
    return price, inputs


def test_sarima_recovers_trend_direction():
    price, inputs = synthetic()
    out = Sarimax(exog=False).forecast(price, inputs, [1, 3, 6])
    assert all(out[h] > price.iloc[-1] for h in (1, 3, 6))


def test_order_reselected_only_in_january(monkeypatch):
    calls = []

    def fake_select(y, exog):
        calls.append(len(y))
        return (0, 1, 0), (0, 0, 0, 12)

    monkeypatch.setattr(sarimax_module, "select_order", fake_select)
    price, inputs = synthetic(years=16)
    m = Sarimax(exog=False)
    for origin in ("2009-01", "2009-03", "2009-07"):
        m.forecast(price.loc[:origin], inputs.loc[:origin], [1])
    assert len(calls) == 1
    m.forecast(price.loc[:"2010-01"], inputs.loc[:"2010-01"], [1])
    assert len(calls) == 2


def test_sarimax_future_exog_shape():
    price, inputs = synthetic()
    out = Sarimax(exog=True).forecast(price, inputs, [1, 3, 6])
    assert sorted(out) == [1, 3, 6]
    assert all(isinstance(v, float) and np.isfinite(v) for v in out.values())


def test_registered_under_both_names():
    assert REGISTRY["sarima"]().name == "sarima"
    assert REGISTRY["sarimax"]().name == "sarimax"

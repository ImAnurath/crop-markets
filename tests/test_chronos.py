import numpy as np
import pandas as pd
import pytest


@pytest.mark.slow
def test_chronos_returns_three_positive_floats():
    from hazelnut.forecast.methods.chronos import ChronosBolt

    idx = pd.period_range("2005-01", periods=180, freq="M")
    t = np.arange(len(idx))
    history = pd.Series(3 + 0.5 * np.sin(2 * np.pi * t / 12) + 0.005 * t, index=idx)
    history.iloc[40] = np.nan  # a missing month is dropped, not passed as NaN
    out = ChronosBolt().forecast(history, pd.DataFrame(index=idx), [1, 3, 6])
    assert sorted(out) == [1, 3, 6]
    assert all(isinstance(v, float) and np.isfinite(v) and v > 0 for v in out.values())


def test_registered():
    from hazelnut.forecast.methods import REGISTRY

    assert "chronos" in REGISTRY

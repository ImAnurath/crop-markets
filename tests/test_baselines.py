import numpy as np
import pandas as pd
import pytest

from hazelnut.forecast.methods import REGISTRY
from hazelnut.forecast.methods.baselines import Naive, SeasonalNaive

EMPTY = pd.DataFrame()


def test_naive_uses_last_valid():
    idx = pd.period_range("2020-01", "2020-04", freq="M")
    history = pd.Series([1.0, 2.0, 3.0, np.nan], index=idx)
    assert Naive().forecast(history, EMPTY, [1, 3, 6]) == {1: 3.0, 3: 3.0, 6: 3.0}


def test_seasonal_naive_uses_same_calendar_month():
    idx = pd.period_range("2010-01", "2012-03", freq="M")
    rng = np.random.default_rng(0)
    history = pd.Series(rng.uniform(1, 5, len(idx)), index=idx)
    for year in (2010, 2011):
        history[pd.Period(f"{year}-06", "M")] = 2.0 * history[pd.Period(f"{year}-03", "M")]
    out = SeasonalNaive().forecast(history, EMPTY, [3])
    assert out[3] == pytest.approx(2.0 * history.iloc[-1])


def test_seasonal_naive_without_pairs_equals_naive():
    idx = pd.period_range("2020-01", "2020-04", freq="M")
    history = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx)
    assert SeasonalNaive().forecast(history, EMPTY, [1, 3, 6]) == {1: 4.0, 3: 4.0, 6: 4.0}


def test_registry_names_match():
    for key, make in REGISTRY.items():
        assert make().name == key
    assert {"naive", "seasonal_naive"} <= set(REGISTRY)

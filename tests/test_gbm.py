import numpy as np

from hazelnut.forecast.methods import REGISTRY
from hazelnut.forecast.methods.gbm import Gbm
from tests.test_features import synthetic


def test_gbm_returns_three_positive_floats():
    history, inputs = synthetic(years=20)
    out = Gbm().forecast(history, inputs, [1, 3, 6])
    assert sorted(out) == [1, 3, 6]
    assert all(isinstance(v, float) and np.isfinite(v) and v > 0 for v in out.values())


def test_gbm_too_little_history_returns_none():
    history, inputs = synthetic(years=5)  # 60 months -> at most 59 labelled rows
    assert Gbm().forecast(history, inputs, [1]) == {1: None}


def test_registered():
    assert REGISTRY["lightgbm"]().name == "lightgbm"

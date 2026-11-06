import numpy as np
import pandas as pd

from hazelnut.forecast.features import FEATURES, make_features, training_set

M = lambda s: pd.Period(s, "M")  # noqa: E731


def synthetic(years=10, seed=0):
    idx = pd.period_range("2000-01", periods=12 * years, freq="M")
    rng = np.random.default_rng(seed)
    history = pd.Series(np.exp(rng.normal(0, 0.1, len(idx)).cumsum()), index=idx)
    inputs = pd.DataFrame(
        {
            "usd_try": np.exp(rng.normal(0.01, 0.02, len(idx)).cumsum()),
            "cpi": rng.uniform(1, 2, len(idx)),
            "exports_kg": rng.uniform(1e6, 2e6, len(idx)),
            "fao_production_t": rng.uniform(5e5, 8e5, len(idx)),
            "crop_estimate_t": rng.uniform(5e4, 1e5, len(idx)),
            "crop_change": rng.normal(0, 0.2, len(idx)),
            "frost_days": rng.uniform(0, 5, len(idx)),
            "volume_kg": rng.uniform(1e6, 5e6, len(idx)),
        },
        index=idx,
    )
    return history, inputs


def test_feature_columns():
    history, inputs = synthetic()
    f = make_features(history, inputs)
    assert list(f.columns) == FEATURES
    assert f.index.equals(history.index)
    assert f.loc[M("2001-08"), "months_since_estimate"] == 0
    assert f.loc[M("2001-07"), "months_since_estimate"] == 11


def test_features_use_no_future_rows():
    history, inputs = synthetic()
    t = M("2005-06")
    before = make_features(history, inputs).loc[t]
    h2, i2 = history.copy(), inputs.copy()
    h2[h2.index > t] *= 3.0
    i2.loc[i2.index > t] = i2.loc[i2.index > t] * 7.0 + 1.0
    after = make_features(h2, i2).loc[t]
    pd.testing.assert_series_equal(before, after)


def test_label_rows_end_at_origin_minus_h():
    history, inputs = synthetic()
    f = make_features(history, inputs)
    for h in (1, 3, 6):
        X, y = training_set(f, history, h)
        assert X.index[-1] == history.index[-1] - h
        assert X.index.equals(y.index)
        assert y.iloc[-1] == np.log(history.iloc[-1]) - np.log(history[history.index[-1] - h])


def test_zero_exports_give_nan_not_inf():
    history, inputs = synthetic()
    inputs.loc[M("2003-02"), "exports_kg"] = 0.0
    f = make_features(history, inputs)
    assert not np.isinf(f.to_numpy(dtype=float)).any()
    assert np.isnan(f.loc[M("2003-02"), "exports_yoy"])
    assert np.isnan(f.loc[M("2004-02"), "exports_yoy"])

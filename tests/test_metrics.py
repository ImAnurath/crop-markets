import pandas as pd
import pytest

from hazelnut.forecast.metrics import is_shock, score, score_by_period

M = lambda s: pd.Period(s, "M")  # noqa: E731


def results():
    rows = [
        # method, origin, horizon, target_month, forecast, actual, fallback
        ("naive", M("2010-01"), 1, M("2010-02"), 1.0, 2.0, False),
        ("naive", M("2010-02"), 1, M("2010-03"), 2.0, 2.0, False),
        ("other", M("2010-01"), 1, M("2010-02"), 2.0, 2.0, False),
        ("other", M("2010-02"), 1, M("2010-03"), 2.0, 2.0, True),
        ("other", M("2010-03"), 1, M("2010-04"), 4.0, 2.0, False),
    ]
    cols = ["method", "origin", "horizon", "target_month", "forecast", "actual", "fallback"]
    return pd.DataFrame(rows, columns=cols)


def test_score_values():
    s = score(results())
    assert list(s.columns) == ["n", "mae", "mape", "skill", "fallback_share"]
    naive, other = s.loc[("naive", 1)], s.loc[("other", 1)]
    assert naive["n"] == 2 and naive["mae"] == pytest.approx(0.5)
    assert naive["mape"] == pytest.approx(25.0)
    assert naive["skill"] == pytest.approx(0.0)
    assert other["n"] == 3 and other["mae"] == pytest.approx(2 / 3)
    assert other["skill"] == pytest.approx(1.0)  # 0 error on the two rows naive also has
    assert other["fallback_share"] == pytest.approx(1 / 3)


def test_score_by_period_splits_calm_and_shock():
    r = results()
    r.loc[0, "target_month"] = M("2014-02")
    r.loc[2, "target_month"] = M("2014-02")
    s = score_by_period(r)
    assert s.index.names == ["method", "horizon", "period"]
    assert s.loc[("naive", 1, "shock"), "mae"] == pytest.approx(1.0)
    assert s.loc[("naive", 1, "calm"), "mae"] == pytest.approx(0.0)
    assert s.loc[("other", 1, "shock"), "skill"] == pytest.approx(1.0)


def test_shock_months():
    assert is_shock(M("2014-06")) and not is_shock(M("2016-01"))
    assert is_shock(M("2005-01")) and is_shock(M("2025-12")) and not is_shock(M("2013-12"))

import numpy as np
import pandas as pd
import pytest

from hazelnut.forecast.methods import REGISTRY
from hazelnut.forecast.methods.season import (
    SeasonRegression,
    season_averages,
    season_backtest,
    season_of,
)

M = lambda s: pd.Period(s, "M")  # noqa: E731


def test_season_of():
    assert season_of(M("2020-09")) == 2020
    assert season_of(M("2021-08")) == 2020
    assert season_of(M("2021-01")) == 2020


def test_season_averages_skips_incomplete():
    idx = pd.period_range("2018-09", "2021-05", freq="M")
    history = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    history[M("2019-12")] = np.nan  # makes season 2019 incomplete
    s = season_averages(history)
    assert list(s.index) == [2018]  # 2020 is incomplete (ends 2021-05)
    assert s[2018] == pytest.approx(np.mean(np.arange(12)))


def synthetic_seasons(first=1999, last=2012, slope=-0.5, seed=1):
    """Monthly price constant within each season; log(S_Y / S_{Y-1}) = slope * crop_change_Y."""
    rng = np.random.default_rng(seed)
    idx = pd.period_range(f"{first}-09", f"{last + 1}-08", freq="M")
    price = pd.Series(np.nan, index=idx)
    inputs = pd.DataFrame({"crop_change": np.nan}, index=idx)
    level = 2.0
    changes = {}
    for y in range(first, last + 1):
        cc = rng.normal(0, 0.3)
        changes[y] = cc
        inputs.loc[M(f"{y}-08") if M(f"{y}-08") in idx else idx[0], "crop_change"] = cc
        if y > first:
            level = level * np.exp(slope * cc)
        price.loc[M(f"{y}-09"):M(f"{y + 1}-08")] = level
    return price, inputs, changes


def test_regression_learns_slope():
    price, inputs, changes = synthetic_seasons()
    origin = M("2011-08")
    out = SeasonRegression().forecast(price.loc[:origin], inputs.loc[:origin], [1, 6])
    expected = price[M("2011-07")] * np.exp(-0.5 * changes[2011])
    assert out[1] == pytest.approx(expected, rel=1e-9)
    assert out[6] == pytest.approx(expected, rel=1e-9)
    assert expected == pytest.approx(price[M("2011-09")])


def test_too_few_seasons_returns_none():
    price, inputs, _ = synthetic_seasons()
    origin = M("2004-08")  # complete seasons with a previous season: 2000..2003 = 4
    out = SeasonRegression().forecast(price.loc[:origin], inputs.loc[:origin], [1, 3, 6])
    assert out == {1: None, 3: None, 6: None}


def test_target_in_unannounced_season_returns_none():
    price, inputs, _ = synthetic_seasons(first=1999, last=2016)
    origin = M("2015-07")
    out = SeasonRegression().forecast(price.loc[:origin], inputs.loc[:origin], [1, 3])
    assert out[3] is None  # 2015-10 is in season 2015, whose estimate comes in 2015-08
    assert out[1] is not None  # 2015-08 is in season 2014, announced in 2014-08


def test_season_backtest_rows():
    price, inputs, _ = synthetic_seasons(first=1999, last=2012)
    table = season_backtest(price, inputs, first_season=2006)
    assert list(table.columns) == ["season", "forecast", "actual", "naive_last_season", "naive_august"]
    assert list(table["season"]) == list(range(2006, 2013))
    assert np.allclose(table["forecast"], table["actual"])


def test_registered():
    assert REGISTRY["season_reg"]().name == "season_reg"
    m = REGISTRY["season_reg_nat"]()
    assert (m.name, m.crop_col) == ("season_reg_nat", "nat_crop_change")

"""Forecasting methods. ``REGISTRY`` maps a method name to a zero-argument constructor;
``QUANTILE_REGISTRY`` does the same for range (quantile) methods."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from hazelnut.forecast.backtest import Method
from hazelnut.forecast.methods.baselines import EmpiricalNaive, Naive, SeasonalNaive
from hazelnut.forecast.methods.chronos import ChronosBolt
from hazelnut.forecast.methods.gbm import Gbm, QuantileGbm
from hazelnut.forecast.methods.sarimax import Sarimax
from hazelnut.forecast.methods.season import SeasonRegression

REGISTRY: dict[str, Callable[[], Method]] = {
    "naive": Naive,
    "seasonal_naive": SeasonalNaive,
    "sarima": partial(Sarimax, exog=False),
    "sarimax": partial(Sarimax, exog=True),
    "season_reg": SeasonRegression,
    "lightgbm": Gbm,
    "chronos": ChronosBolt,
}

# Range methods: each has ``quantiles(history, inputs, horizons, levels)`` (see intervals.py).
VOL_WINDOW = 12  # months of 1-month log changes behind the volatility scaling

QUANTILE_REGISTRY: dict[str, Callable[[], object]] = {
    "naive_emp": EmpiricalNaive,
    "naive_vol": partial(EmpiricalNaive, vol_window=VOL_WINDOW),
    "sarima": partial(Sarimax, exog=False),
    "chronos": ChronosBolt,
    "lightgbm_q": QuantileGbm,
}

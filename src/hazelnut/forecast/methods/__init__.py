"""Forecasting methods. ``REGISTRY`` maps a method name to a zero-argument constructor."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from hazelnut.forecast.backtest import Method
from hazelnut.forecast.methods.baselines import Naive, SeasonalNaive
from hazelnut.forecast.methods.sarimax import Sarimax

REGISTRY: dict[str, Callable[[], Method]] = {
    "naive": Naive,
    "sarima": partial(Sarimax, exog=False),
    "sarimax": partial(Sarimax, exog=True),
}

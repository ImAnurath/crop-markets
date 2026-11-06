"""Forecasting methods. ``REGISTRY`` maps a method name to a zero-argument constructor."""

from __future__ import annotations

from collections.abc import Callable

from hazelnut.forecast.backtest import Method
from hazelnut.forecast.methods.baselines import Naive, SeasonalNaive

REGISTRY: dict[str, Callable[[], Method]] = {
    "naive": Naive,
    "seasonal_naive": SeasonalNaive,
}

"""Forecasting methods. ``REGISTRY`` maps a method name to a zero-argument constructor.

``REGISTRY`` is for the USD target; ``TRY_REGISTRY`` is for the lira target
(``dataset.load_dataset_try``). Its baseline keeps the name "naive" (lira naive).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from hazelnut.forecast.backtest import Method
from hazelnut.forecast.methods.baselines import Naive, SeasonalNaive
from hazelnut.forecast.methods.chronos import ChronosBolt
from hazelnut.forecast.methods.gbm import Gbm
from hazelnut.forecast.methods.lira import Composed, Renamed, TryDrift
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

TRY_REGISTRY: dict[str, Callable[[], Method]] = {
    "naive": Naive,
    "try_drift_12": partial(TryDrift, 12),
    "try_drift_36": partial(TryDrift, 36),
    "composed_fx_drift_12": partial(Composed, "drift", 12),
    "composed_fx_drift_36": partial(Composed, "drift", 36),
    "composed_fx_spot": partial(Composed, "spot"),
    "composed_fx_spot_drift_12": partial(Composed, "spot_drift", 12),
    "composed_fx_spot_drift_36": partial(Composed, "spot_drift", 36),
    "composed_fx_infl": partial(Composed, "infl"),
    "try_sarima": lambda: Renamed(Sarimax(exog=False), "try_sarima"),
    "try_lightgbm": lambda: Renamed(Gbm(), "try_lightgbm"),
}

"""Forecasting methods. Each registry maps a method name to a zero-argument constructor.

- ``REGISTRY``: point methods for the USD target.
- ``QUANTILE_REGISTRY``: range (quantile) methods for the USD target.
- ``TRY_REGISTRY``: point methods for the lira target (``dataset.load_dataset_try``). Its
  baseline keeps the name "naive" (lira naive).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from hazelnut.forecast.backtest import Method
from hazelnut.forecast.methods.baselines import EmpiricalNaive, Naive, SeasonalNaive
from hazelnut.forecast.methods.chronos import ChronosBolt
from hazelnut.forecast.methods.gbm import Gbm, QuantileGbm
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
    # Same methods with the official national crop estimate in place of the Giresun one.
    "sarimax_nat": partial(Sarimax, exog=True, crop_col="nat_crop_change", name="sarimax_nat"),
    "season_reg_nat": partial(SeasonRegression, crop_col="nat_crop_change", name="season_reg_nat"),
    "lightgbm_nat": partial(Gbm, crop_col="nat_crop_change", name="lightgbm_nat"),
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

"""Seasonal ARIMA on log price, with or without outside inputs (SARIMAX).

- Model: log(price), order (p, 1, q), seasonal order (P, 0, Q, 12), with a drift term.
- Order: chosen by AIC on the history only, over p, q in {0, 1, 2} and P, Q in {0, 1}.
  It is re-chosen once per origin year (in January, or at the first origin of a run),
  and the model is refit with that order at every origin.
- Inputs (sarimax only): crop_change and fx_ret_1 = log(usd_try_t / usd_try_{t-1}).
  In the forecast window crop_change is held at its last value and fx_ret_1 is 0.
"""

from __future__ import annotations

import itertools
import warnings
from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.stats import norm
from statsmodels.tsa.statespace.sarimax import SARIMAX

Order = tuple[int, int, int]
SeasonalOrder = tuple[int, int, int, int]
GRID = [
    ((p, 1, q), (P, 0, Q, 12))
    for p, q, P, Q in itertools.product((0, 1, 2), (0, 1, 2), (0, 1), (0, 1))
]
TREND = "c"  # with d = 1 this is a drift in log price


def _fit(y: np.ndarray, exog: np.ndarray | None, order: Order, seasonal: SeasonalOrder):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = SARIMAX(y, exog=exog, order=order, seasonal_order=seasonal, trend=TREND)
        return model.fit(disp=False)


def select_order(y: np.ndarray, exog: np.ndarray | None) -> tuple[Order, SeasonalOrder]:
    best, best_aic = None, np.inf
    for order, seasonal in GRID:
        try:
            aic = _fit(y, exog, order, seasonal).aic
        except Exception:
            continue
        if np.isfinite(aic) and aic < best_aic:
            best, best_aic = (order, seasonal), aic
    if best is None:
        raise RuntimeError("no SARIMA order could be fitted")
    return best


def exog_frame(inputs: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "crop_change": inputs["crop_change"],
            "fx_ret_1": np.log(inputs["usd_try"]).diff(),
        },
        index=inputs.index,
    )


class Sarimax:
    def __init__(self, exog: bool):
        self.exog = exog
        self.name = "sarimax" if exog else "sarima"
        self._orders: dict[int, tuple[Order, SeasonalOrder]] = {}

    def _fit_at(self, history: pd.Series, inputs: pd.DataFrame, steps: int):
        """The fitted model at this origin and the future inputs, or None if too little data."""
        origin = history.index[-1]
        y = np.log(history)
        X = None
        if self.exog:
            X = exog_frame(inputs.loc[: origin])
            bad = X.isna().any(axis=1)
            if bad.any():
                start = bad[bad].index[-1] + 1  # keep the contiguous complete tail
                y, X = y.loc[start:], X.loc[start:]
            if len(y) < 36:
                return None

        if origin.year not in self._orders:
            self._orders[origin.year] = select_order(
                y.to_numpy(), None if X is None else X.to_numpy()
            )
        order, seasonal = self._orders[origin.year]
        result = _fit(y.to_numpy(), None if X is None else X.to_numpy(), order, seasonal)

        future = None
        if X is not None:
            future = np.column_stack(
                [np.full(steps, X["crop_change"].iloc[-1]), np.zeros(steps)]
            )
        return result, future

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        steps = max(horizons)
        fitted = self._fit_at(history, inputs, steps)
        if fitted is None:
            return {h: None for h in horizons}
        result, future = fitted
        path = np.asarray(result.forecast(steps=steps, exog=future))
        return {h: float(np.exp(path[h - 1])) for h in horizons}

    def quantiles(self, history, inputs, horizons: Sequence[int], levels: Sequence[float]):
        """The model's own prediction intervals: normal in log price, so exp(mean + z * se)."""
        steps = max(horizons)
        fitted = self._fit_at(history, inputs, steps)
        if fitted is None:
            return {h: None for h in horizons}
        result, future = fitted
        pred = result.get_forecast(steps=steps, exog=future)
        mean, se = np.asarray(pred.predicted_mean), np.asarray(pred.se_mean)
        z = norm.ppf(np.asarray(levels, dtype=float))
        return {h: list(np.exp(mean[h - 1] + z * se[h - 1])) for h in horizons}

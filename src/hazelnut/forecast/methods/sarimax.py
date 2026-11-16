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


def exog_frame(inputs: pd.DataFrame, crop_col: str = "crop_change") -> pd.DataFrame:
    return pd.DataFrame(
        {
            crop_col: inputs[crop_col],
            "fx_ret_1": np.log(inputs["usd_try"]).diff(),
        },
        index=inputs.index,
    )


class Sarimax:
    """``crop_col`` picks the crop input: the Giresun estimate (default) or nat_crop_change."""

    def __init__(self, exog: bool, crop_col: str = "crop_change", name: str | None = None):
        self.exog = exog
        self.crop_col = crop_col
        self.name = name or ("sarimax" if exog else "sarima")
        self._orders: dict[int, tuple[Order, SeasonalOrder]] = {}

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        origin = history.index[-1]
        y = np.log(history)
        X = None
        if self.exog:
            X = exog_frame(inputs.loc[: origin], self.crop_col)
            bad = X.isna().any(axis=1)
            if bad.any():
                start = bad[bad].index[-1] + 1  # keep the contiguous complete tail
                y, X = y.loc[start:], X.loc[start:]
            if len(y) < 36:
                return {h: None for h in horizons}

        if origin.year not in self._orders:
            self._orders[origin.year] = select_order(
                y.to_numpy(), None if X is None else X.to_numpy()
            )
        order, seasonal = self._orders[origin.year]
        result = _fit(y.to_numpy(), None if X is None else X.to_numpy(), order, seasonal)

        steps = max(horizons)
        future = None
        if X is not None:
            future = np.column_stack(
                [np.full(steps, X[self.crop_col].iloc[-1]), np.zeros(steps)]
            )
        path = np.asarray(result.forecast(steps=steps, exog=future))
        return {h: float(np.exp(path[h - 1])) for h in horizons}

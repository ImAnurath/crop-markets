"""Baselines every other method is judged against."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def last_price(history: pd.Series) -> float:
    return float(history.dropna().iloc[-1])


class Naive:
    """Next month (and every later month) = the last observed price."""

    name = "naive"

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        p = last_price(history)
        return {h: p for h in horizons}


class SeasonalNaive:
    """Last price times the average past log change from this calendar month to month + h."""

    name = "seasonal_naive"

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        p = last_price(history)
        origin = history.index[-1]
        log_p = np.log(history)
        same_month = [m for m in history.index if m.month == origin.month]
        out = {}
        for h in horizons:
            changes = [
                log_p[m + h] - log_p[m]
                for m in same_month
                if m + h <= origin and np.isfinite(log_p[m]) and np.isfinite(log_p[m + h])
            ]
            out[h] = p * float(np.exp(np.mean(changes))) if changes else p
        return out

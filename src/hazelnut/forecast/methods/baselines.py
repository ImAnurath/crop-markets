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


MIN_CHANGES = 24  # fewer past h-month changes than this: no range


class EmpiricalNaive:
    """Range around the naive forecast from past h-month log price changes.

    Quantile tau of the price h months ahead = last price * exp(quantile tau of every past
    change log_price[s+h] - log_price[s] with s+h <= origin), an expanding window.

    With ``vol_window`` each past change is first divided by the volatility known at its start,
    sigma_s = std of the 1-month log changes in the ``vol_window`` months up to s, and the
    quantiles of these standardised changes are multiplied by today's sigma. Ranges then widen
    after turbulent months and narrow in calm ones (shocks cluster).
    """

    def __init__(self, vol_window: int | None = None):
        self.vol_window = vol_window
        self.name = "naive_emp" if vol_window is None else "naive_vol"

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        return Naive().forecast(history, inputs, horizons)

    def quantiles(self, history, inputs, horizons: Sequence[int], levels: Sequence[float]):
        p = last_price(history)
        log_p = np.log(history.astype(float))
        sigma = None
        if self.vol_window is not None:
            sigma = log_p.diff().rolling(self.vol_window, min_periods=self.vol_window // 2).std()
            now = sigma.dropna()
            if now.empty or now.index[-1] < history.index[-1] - 2:
                return {h: None for h in horizons}
            sigma_now = float(now.iloc[-1])
        out: dict[int, list[float] | None] = {}
        for h in horizons:
            change = log_p.shift(-h) - log_p  # indexed by the start month s; NaN past origin - h
            if sigma is not None:
                change = change / sigma
            change = change.replace([np.inf, -np.inf], np.nan).dropna()
            if len(change) < MIN_CHANGES:
                out[h] = None
                continue
            q = np.quantile(change.to_numpy(), levels)
            if sigma is not None:
                q = q * sigma_now
            out[h] = list(p * np.exp(q))
        return out

"""Methods for the lira target (TRY/kg, ``dataset.load_dataset_try``).

All of them start from the last observed lira price p_t and only differ in the expected log
change they add over h months:

- try_drift_W:    h * trailing mean monthly log change of the lira price over W months.
- composed_*:     USD naive x an FX forecast. With p_usd = p_t / usd_try_t this is
                  p_t * fx_forecast / usd_try_t, so only the FX side adds anything (USD naive x
                  FX naive is exactly lira naive, see ``Composed``).
  FX forecasts:   drift_W: usd_try_t * exp(h * trailing mean monthly log change over W months)
                  spot:    usd_try_eom_t (last daily quote of month t)
                  spot_drift_W: usd_try_eom_t * exp((h - 0.5) * drift_W); the target month's
                           average sits h - 0.5 months after the end of month t
                  infl:    usd_try_t * exp(h * (TR CPI 12-month log inflation - US) / 12), with
                           CPI lagged one month (inputs) and US inflation fixed at 2.5% a year
                           (no US CPI in the data; 2005-2024 average was about 2.5%).

Every rule reads only ``history`` and ``inputs`` up to the origin, which the harness has
already truncated, and the inputs frame respects the information timing rules.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from hazelnut.forecast.methods.baselines import last_price

US_INFLATION = 0.025  # per year, log approx.


def trailing_drift(series: pd.Series, window: int) -> float | None:
    """Mean monthly log change over the last ``window`` months: log(x_t / x_{t-W}) / W."""
    end = series.index[-1]
    start = end - window
    if start not in series.index:
        return None
    a, b = float(series[start]), float(series[end])
    if not (np.isfinite(a) and np.isfinite(b) and a > 0 and b > 0):
        return None
    return float(np.log(b / a) / window)


class TryDrift:
    """Last lira price times exp(h * trailing lira drift)."""

    def __init__(self, window: int):
        self.window = window
        self.name = f"try_drift_{window}"

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        p = last_price(history)
        d = trailing_drift(history, self.window)
        if d is None:
            return {h: None for h in horizons}
        return {h: p * float(np.exp(h * d)) for h in horizons}


class Composed:
    """USD naive x FX forecast, for FX rule ``fx`` in naive, drift, spot, spot_drift, infl."""

    def __init__(self, fx: str, window: int | None = None):
        if fx not in {"naive", "drift", "spot", "spot_drift", "infl"}:
            raise ValueError(f"unknown FX rule {fx!r}")
        self.fx, self.window = fx, window
        self.name = "composed_fx_" + fx + (f"_{window}" if window else "")

    def fx_forecast(self, inputs: pd.DataFrame, h: int) -> float | None:
        fx = inputs["usd_try"]
        avg = float(fx.iloc[-1])
        if self.fx == "naive":
            return avg
        if self.fx == "drift":
            d = trailing_drift(fx, self.window)
            return None if d is None else avg * float(np.exp(h * d))
        spot = float(inputs["usd_try_eom"].iloc[-1])
        if self.fx == "spot":
            return spot
        if self.fx == "spot_drift":
            d = trailing_drift(fx, self.window)
            return None if d is None else spot * float(np.exp((h - 0.5) * d))
        # infl
        cpi = inputs["cpi"]
        origin = cpi.index[-1]
        if origin - 12 not in cpi.index:
            return None
        tr = float(np.log(cpi[origin] / cpi[origin - 12]))
        return avg * float(np.exp(h * (tr - US_INFLATION) / 12))

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        origin = history.index[-1]
        inputs = inputs.loc[:origin]
        if inputs.index[-1] != origin:
            return {h: None for h in horizons}
        p_usd = last_price(history) / float(inputs["usd_try"].iloc[-1])
        out = {}
        for h in horizons:
            fx = self.fx_forecast(inputs, h)
            out[h] = None if fx is None or not np.isfinite(fx) else p_usd * fx
        return out


class Renamed:
    """Run an existing method under another name (the lira results live in their own table)."""

    def __init__(self, method, name: str):
        self.method, self.name = method, name

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        return self.method.forecast(history, inputs, horizons)

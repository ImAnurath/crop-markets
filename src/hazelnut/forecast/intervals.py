"""Walk-forward backtest for range (quantile) forecasts.

A range method has ``quantiles(history, inputs, horizons, levels)`` returning, per horizon, the
price quantiles (USD/kg) at ``levels``, or ``None`` when it can't forecast that horizon. As in
``backtest.run_backtest``, the method sees only data up to each origin. A failed horizon falls
back to the naive-empirical range (``EmpiricalNaive``) and is marked ``fallback=True``; if even
that has too little history, the row is dropped.
Quantiles are sorted per row, so they never cross.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np
import pandas as pd

from hazelnut.forecast.dataset import FIRST_ORIGIN, HORIZONS
from hazelnut.forecast.methods.baselines import EmpiricalNaive

LEVELS = (0.05, 0.1, 0.5, 0.9, 0.95)


def column(level: float) -> str:
    return f"q{round(level * 100):02d}"


class RangeMethod(Protocol):
    name: str

    def quantiles(
        self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int],
        levels: Sequence[float],
    ) -> dict[int, Sequence[float] | None]: ...


def _valid(values, n: int) -> bool:
    if values is None or len(values) != n:
        return False
    a = np.asarray(values, dtype=float)
    return bool(np.all(np.isfinite(a)) and np.all(a > 0))


def _call(method, history, inputs, horizons, levels) -> dict:
    """Ask for all horizons at once; if that raises, retry one horizon at a time."""
    try:
        return dict(method.quantiles(history, inputs, list(horizons), list(levels)))
    except Exception:
        pass
    out = {}
    for h in horizons:
        try:
            out[h] = method.quantiles(history, inputs, [h], list(levels)).get(h)
        except Exception:
            out[h] = None
    return out


def run_quantile_backtest(
    method: RangeMethod,
    target: pd.Series,
    inputs: pd.DataFrame,
    first_origin: pd.Period = FIRST_ORIGIN,
    horizons: Sequence[int] = HORIZONS,
    levels: Sequence[float] = LEVELS,
) -> pd.DataFrame:
    """One row per (origin, horizon): method, origin, horizon, target_month, actual, fallback and
    one column per level (q05, q10, q50, q90, q95)."""
    last = target.index[-1]
    fallback_method = EmpiricalNaive()
    rows = []
    for origin in pd.period_range(first_origin, last - 1, freq="M"):
        wanted = [h for h in horizons if origin + h <= last and pd.notna(target[origin + h])]
        if not wanted:
            continue
        history, visible = target.loc[:origin], inputs.loc[:origin]
        got = _call(method, history, visible, wanted, levels)
        backup = None
        for h in wanted:
            values, ok = got.get(h), _valid(got.get(h), len(levels))
            if not ok:
                backup = backup or fallback_method.quantiles(history, visible, wanted, levels)
                values = backup[h]
                if values is None:  # too little history even for the fallback
                    continue
            rows.append(
                (method.name, origin, h, origin + h, float(target[origin + h]), not ok,
                 *np.sort(np.asarray(values, dtype=float)))
            )
    columns = ["method", "origin", "horizon", "target_month", "actual", "fallback"]
    return pd.DataFrame(rows, columns=columns + [column(lv) for lv in levels])

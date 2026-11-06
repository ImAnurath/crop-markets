"""Walk-forward backtest: every method sees only the data available at each origin."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

import pandas as pd

from hazelnut.forecast.dataset import FIRST_ORIGIN, HOLDOUT_MONTHS, HORIZONS

COLUMNS = ["method", "origin", "horizon", "target_month", "forecast", "actual", "fallback"]


class Method(Protocol):
    name: str

    def forecast(
        self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]
    ) -> dict[int, float | None]:
        """Forecast the price (USD/kg) ``h`` months after ``history.index[-1]``.

        ``None`` for a horizon (or a raised exception) means "can't forecast this one";
        the harness then uses the naive forecast and marks the row ``fallback=True``.
        """
        ...


def split_dev(target: pd.Series, inputs: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Drop the holdout months (the last ``HOLDOUT_MONTHS`` of the target)."""
    dev = target.iloc[:-HOLDOUT_MONTHS]
    return dev, inputs.loc[dev.index]


def holdout_start(target: pd.Series) -> pd.Period:
    return target.index[-HOLDOUT_MONTHS]


def _valid(value) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def _call(method: Method, history, inputs, horizons) -> dict[int, float | None]:
    """Ask for all horizons at once; if that raises, retry one horizon at a time."""
    try:
        return dict(method.forecast(history, inputs, list(horizons)))
    except Exception:
        pass
    out: dict[int, float | None] = {}
    for h in horizons:
        try:
            out[h] = method.forecast(history, inputs, [h]).get(h)
        except Exception:
            out[h] = None
    return out


def run_backtest(
    method: Method,
    target: pd.Series,
    inputs: pd.DataFrame,
    first_origin: pd.Period = FIRST_ORIGIN,
    score_from: pd.Period | None = None,
    horizons: Sequence[int] = HORIZONS,
) -> pd.DataFrame:
    last = target.index[-1]
    rows = []
    for origin in pd.period_range(first_origin, last - 1, freq="M"):
        wanted = []
        for h in horizons:
            month = origin + h
            if month > last or pd.isna(target[month]):
                continue
            if score_from is not None and month < score_from:
                continue
            wanted.append(h)
        if not wanted:
            continue
        history = target.loc[:origin]
        forecasts = _call(method, history, inputs.loc[:origin], wanted)
        naive = float(history.dropna().iloc[-1])
        for h in wanted:
            value = forecasts.get(h)
            ok = _valid(value)
            rows.append(
                (method.name, origin, h, origin + h, float(value) if ok else naive,
                 float(target[origin + h]), not ok)
            )
    return pd.DataFrame(rows, columns=COLUMNS)

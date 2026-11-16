"""Season-ahead regression: predict the average price of the coming season from the crop estimate.

A season runs from September of year Y to August of Y+1 (season Y). Each August, when the
Giresun crop estimate for harvest Y comes out, the model predicts

    log(S_Y / S_{Y-1}) = a + b * crop_change_Y

with OLS on every past complete season. To sit in the monthly table, every target month in
season Y gets the predicted S_Y as its forecast, but only once the estimate is out (origin is
August Y or later). Before that, the method has nothing to say and the harness uses naive.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

MIN_SEASONS = 5
FIRST_SEASON = 2005


def season_of(month: pd.Period) -> int:
    return month.year if month.month >= 9 else month.year - 1


def season_averages(history: pd.Series) -> pd.Series:
    """Mean price per season, only for seasons with all 12 months present."""
    seasons = np.array([season_of(m) for m in history.index])
    grouped = history.groupby(seasons)
    complete = grouped.count() == 12
    return grouped.mean()[complete].astype(float)


def _crop_change(inputs: pd.DataFrame, year: int, crop_col: str = "crop_change") -> float:
    month = pd.Period(f"{year}-08", "M")
    if month not in inputs.index:
        return np.nan
    return float(inputs.at[month, crop_col])


def predict_season(
    history: pd.Series, inputs: pd.DataFrame, year: int, crop_col: str = "crop_change"
) -> float | None:
    """Predicted S_year from data up to history.index[-1], or None when it can't be made."""
    averages = season_averages(history)
    rows, labels = [], []
    for y, s in averages.items():
        cc = _crop_change(inputs, y, crop_col)
        if y - 1 in averages.index and np.isfinite(cc):
            rows.append([1.0, cc])
            labels.append(np.log(s / averages[y - 1]))
    cc_now = _crop_change(inputs, year, crop_col)
    if len(rows) < MIN_SEASONS or year - 1 not in averages.index or not np.isfinite(cc_now):
        return None
    coef, *_ = np.linalg.lstsq(np.array(rows), np.array(labels), rcond=None)
    return float(averages[year - 1] * np.exp(coef[0] + coef[1] * cc_now))


class SeasonRegression:
    """``crop_col`` picks the crop input: the Giresun estimate (default) or nat_crop_change."""

    def __init__(self, crop_col: str = "crop_change", name: str = "season_reg"):
        self.crop_col = crop_col
        self.name = name

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        origin = history.index[-1]
        cache: dict[int, float | None] = {}
        out: dict[int, float | None] = {}
        for h in horizons:
            year = season_of(origin + h)
            if origin < pd.Period(f"{year}-08", "M"):
                out[h] = None
                continue
            if year not in cache:
                cache[year] = predict_season(history, inputs, year, self.crop_col)
            out[h] = cache[year]
        return out


def season_backtest(
    target: pd.Series,
    inputs: pd.DataFrame,
    first_season: int = FIRST_SEASON,
    crop_col: str = "crop_change",
) -> pd.DataFrame:
    """One row per August origin (season Y predicted in August Y) whose season is complete."""
    averages = season_averages(target)
    rows = []
    for year in sorted(y for y in averages.index if y >= first_season):
        origin = pd.Period(f"{year}-08", "M")
        if origin not in target.index:
            continue
        history = target.loc[:origin]
        forecast = predict_season(history, inputs.loc[:origin], year, crop_col)
        rows.append(
            (
                year,
                np.nan if forecast is None else forecast,
                averages[year],
                averages.get(year - 1, np.nan),
                float(history.dropna().iloc[-1]),
            )
        )
    return pd.DataFrame(
        rows, columns=["season", "forecast", "actual", "naive_last_season", "naive_august"]
    )

"""Scores for backtest results: MAE (USD/kg), MAPE (%), skill vs a baseline, fallback share."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hazelnut.forecast.dataset import SHOCK_PERIODS

_SHOCKS = [(pd.Period(a, "M"), pd.Period(b, "M")) for a, b in SHOCK_PERIODS]
SCORE_COLUMNS = ["n", "mae", "mape", "skill", "fallback_share"]


def is_shock(month: pd.Period) -> bool:
    return any(start <= month <= end for start, end in _SHOCKS)


def _score(results: pd.DataFrame, baseline: str, keys: list[str]) -> pd.DataFrame:
    r = results.assign(abs_err=(results["forecast"] - results["actual"]).abs())
    r["pct_err"] = 100 * r["abs_err"] / r["actual"].abs()
    base = r[r["method"] == baseline][keys[1:] + ["origin", "abs_err"]].rename(
        columns={"abs_err": "base_err"}
    )
    out = []
    for key, g in r.groupby(keys, sort=True):
        shared = g.merge(base, on=keys[1:] + ["origin"], how="inner")
        base_mae = shared["base_err"].mean() if len(shared) else np.nan
        skill = 1 - shared["abs_err"].mean() / base_mae if base_mae and base_mae > 0 else np.nan
        out.append(
            (*key, len(g), g["abs_err"].mean(), g["pct_err"].mean(), skill, g["fallback"].mean())
        )
    return pd.DataFrame(out, columns=keys + SCORE_COLUMNS).set_index(keys)


def score(results: pd.DataFrame, baseline: str = "naive") -> pd.DataFrame:
    """Indexed (method, horizon). Skill = 1 - MAE / baseline MAE on the same (origin, horizon) rows."""
    return _score(results, baseline, ["method", "horizon"])


def score_by_period(results: pd.DataFrame, baseline: str = "naive") -> pd.DataFrame:
    """Like ``score`` but split by target month into "calm" and "shock" periods."""
    period = np.where(results["target_month"].map(is_shock), "shock", "calm")
    return _score(results.assign(period=period), baseline, ["method", "horizon", "period"])

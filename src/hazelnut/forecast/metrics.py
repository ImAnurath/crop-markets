"""Scores for backtest results: MAE (USD/kg), MAPE (%), skill vs a baseline, fallback share."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hazelnut.forecast.dataset import LIRA_CRISES, SHOCK_PERIODS

_SHOCKS = [(pd.Period(a, "M"), pd.Period(b, "M")) for a, b in SHOCK_PERIODS]
_CRISES = [(pd.Period(a, "M"), pd.Period(b, "M")) for a, b in LIRA_CRISES]
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


def is_lira_crisis(month: pd.Period) -> bool:
    return any(start <= month <= end for start, end in _CRISES)


RELATIVE_COLUMNS = ["n", "mae", "mae_ratio", "mape", "mape_ratio", "log_mae", "fallback_share"]


def score_relative(
    results: pd.DataFrame, baseline: str = "naive", by: str | None = None
) -> pd.DataFrame:
    """Scale-free scores for a target that grows by orders of magnitude (the lira price).

    mae_ratio / mape_ratio = method MAE / MAPE over baseline MAE / MAPE on the shared
    (origin, horizon) rows (below 1 beats the baseline). log_mae = mean |log forecast - log
    actual| (x100 is roughly a percent error). ``by`` = "crisis" adds a calm / lira-crisis split.
    """
    r = results.assign(
        abs_err=(results["forecast"] - results["actual"]).abs(),
        pct_err=100 * (results["forecast"] - results["actual"]).abs() / results["actual"].abs(),
        log_err=np.abs(np.log(results["forecast"] / results["actual"])),
    )
    keys = ["method", "horizon"]
    if by == "crisis":
        r["period"] = np.where(r["target_month"].map(is_lira_crisis), "crisis", "calm")
        keys.append("period")
    base = r[r["method"] == baseline][keys[1:] + ["origin", "abs_err", "pct_err"]].rename(
        columns={"abs_err": "base_abs", "pct_err": "base_pct"}
    )
    out = []
    for key, g in r.groupby(keys, sort=True):
        shared = g.merge(base, on=keys[1:] + ["origin"], how="inner")
        ratio = lambda a, b: a.mean() / b.mean() if len(shared) and b.mean() > 0 else np.nan  # noqa: E731
        out.append((
            *key, len(g), g["abs_err"].mean(),
            ratio(shared["abs_err"], shared["base_abs"]),
            g["pct_err"].mean(),
            ratio(shared["pct_err"], shared["base_pct"]),
            g["log_err"].mean(), g["fallback"].mean(),
        ))
    return pd.DataFrame(out, columns=keys + RELATIVE_COLUMNS).set_index(keys)


def diebold_mariano(loss_a: np.ndarray, loss_b: np.ndarray, h: int) -> tuple[float, float]:
    """DM statistic and two-sided p-value for mean(loss_a - loss_b) = 0.

    h-step forecasts from consecutive origins overlap, so the variance uses a Newey-West
    (Bartlett) estimate with h - 1 lags. Normal approximation; negative stat = a is better.
    """
    from scipy.stats import norm

    d = np.asarray(loss_a, float) - np.asarray(loss_b, float)
    n = len(d)
    u = d - d.mean()
    var = u @ u / n
    for lag in range(1, h):
        var += 2 * (1 - lag / h) * (u[lag:] @ u[:-lag]) / n
    if var <= 0:
        return float("nan"), float("nan")
    stat = d.mean() / np.sqrt(var / n)
    return float(stat), float(2 * norm.sf(abs(stat)))

"""Scores for backtest results: MAE (USD/kg), MAPE (%), skill vs a baseline, fallback share.
Quantile forecasts: interval coverage and width, interval score and pinball loss."""

from __future__ import annotations

import re

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


# ---- Quantile (range) forecasts -------------------------------------------------------------
# Results from ``intervals.run_quantile_backtest``: one column per level, named q05, q10, ...
# The 80% interval is q10..q90 and the 90% interval is q05..q95.

QUANTILE_SCORE_COLUMNS = [
    "n", "cov80", "width80", "is80", "cov90", "width90", "is90", "pinball", "skill",
    "fallback_share",
]
_SUMMED = ["cov80", "width80", "is80", "cov90", "width90", "is90", "pinball"]


def quantile_columns(results: pd.DataFrame) -> dict[str, float]:
    """Map each quantile column (q05, q10, ...) to its level (0.05, 0.10, ...)."""
    return {c: int(c[1:]) / 100 for c in results.columns if re.fullmatch(r"q\d\d", c)}


def pinball(actual, quantile, level: float):
    """Pinball (quantile) loss of a quantile forecast at ``level``. Lower is better."""
    diff = np.asarray(actual, dtype=float) - np.asarray(quantile, dtype=float)
    return np.maximum(level * diff, (level - 1) * diff)


def interval_score(actual, lower, upper, alpha: float):
    """Gneiting-Raftery score of a central (1 - alpha) interval: its width plus 2 / alpha times
    the distance by which the actual falls outside it. Lower is better."""
    y, lo, hi = (np.asarray(v, dtype=float) for v in (actual, lower, upper))
    return (hi - lo) + (2 / alpha) * (np.maximum(lo - y, 0) + np.maximum(y - hi, 0))


def _quantile_rows(results: pd.DataFrame) -> pd.DataFrame:
    y = results["actual"]
    r = results.copy()
    for lo, hi, tag, alpha in (("q10", "q90", "80", 0.2), ("q05", "q95", "90", 0.1)):
        r[f"cov{tag}"] = ((results[lo] <= y) & (y <= results[hi])).astype(float)
        r[f"width{tag}"] = results[hi] - results[lo]
        r[f"is{tag}"] = interval_score(y, results[lo], results[hi], alpha)
    levels = quantile_columns(results)
    r["pinball"] = np.mean([pinball(y, results[c], lv) for c, lv in levels.items()], axis=0)
    return r


def _score_quantiles(results: pd.DataFrame, baseline: str, keys: list[str]) -> pd.DataFrame:
    r = _quantile_rows(results)
    base = r[r["method"] == baseline][keys[1:] + ["origin", "pinball"]].rename(
        columns={"pinball": "base_pinball"}
    )
    out = []
    for key, g in r.groupby(keys, sort=True):
        shared = g.merge(base, on=keys[1:] + ["origin"], how="inner")
        base_loss = shared["base_pinball"].mean() if len(shared) else np.nan
        skill = 1 - shared["pinball"].mean() / base_loss if base_loss and base_loss > 0 else np.nan
        out.append((*key, len(g), *g[_SUMMED].mean(), skill, g["fallback"].mean()))
    return pd.DataFrame(out, columns=keys + QUANTILE_SCORE_COLUMNS).set_index(keys)


def score_quantiles(results: pd.DataFrame, baseline: str = "naive_emp") -> pd.DataFrame:
    """Indexed (method, horizon). cov80 / cov90 = share of actuals inside the 80% / 90% interval,
    width in USD/kg, is = interval score, pinball = mean pinball loss over all levels (twice it
    approximates the CRPS). skill = 1 - pinball / baseline pinball on the same (origin, horizon)
    rows."""
    return _score_quantiles(results, baseline, ["method", "horizon"])


def score_quantiles_by_period(results: pd.DataFrame, baseline: str = "naive_emp") -> pd.DataFrame:
    """Like ``score_quantiles`` but split by target month into "calm" and "shock" periods."""
    period = np.where(results["target_month"].map(is_shock), "shock", "calm")
    return _score_quantiles(
        results.assign(period=period), baseline, ["method", "horizon", "period"]
    )


# ---- Lira (TRY) target ----------------------------------------------------------------------

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

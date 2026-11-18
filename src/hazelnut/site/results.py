"""Results tables for the site, built from the committed backtest CSVs (never re-run).

Reads ``<backtest_dir>/{dev,holdout,dev_try,dev_ranges,dev_late}/<method>.csv`` (file stem =
method name) and writes small tables into ``out_dir``. A missing folder just skips its tables.
Each crop names its own folder (its module's ``BACKTEST_DIR``) and crop-estimate check methods.
Scoring mirrors scripts/run_backtest.py, run_intervals.py, lira_findings.py and
crop_estimate_check.py by calling the same ``hazelnut.forecast.metrics`` functions.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from hazelnut.forecast.metrics import (
    diebold_mariano,
    is_lira_crisis,
    score,
    score_by_period,
    score_quantiles,
    score_relative,
)

HOLDOUT_NOTE = "scored once, never tuned on"


def _load(folder: Path) -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in sorted(folder.glob("*.csv"))] if folder.is_dir() else []
    if not frames:
        return pd.DataFrame()
    r = pd.concat(frames, ignore_index=True)
    for col in ("origin", "target_month"):
        r[col] = pd.PeriodIndex(r[col], freq="M")
    r["fallback"] = r["fallback"].astype(bool)
    return r


def _board(results: pd.DataFrame) -> pd.DataFrame:
    s = score(results).reset_index()
    s["ratio"] = 1 - s["skill"]
    return s[["method", "horizon", "n", "mae", "ratio"]]


def _shocks(results: pd.DataFrame) -> pd.DataFrame:
    s = score_by_period(results).reset_index()
    s["ratio"] = 1 - s["skill"]
    return s[["method", "horizon", "period", "mae", "ratio"]]


def _dm_p(r: pd.DataFrame, method: str, horizon: int) -> float:
    """DM p-value vs lira naive on |log error| (as scripts/lira_findings.py), shared origins."""
    g = r.assign(loss=np.abs(np.log(r["forecast"] / r["actual"])))
    g = g[g["horizon"] == horizon].sort_values("origin")
    a = g[g["method"] == method].set_index("origin")["loss"]
    b = g[g["method"] == "naive"].set_index("origin")["loss"]
    idx = a.index.intersection(b.index)
    if len(idx) < 3 or method == "naive":
        return float("nan")
    return diebold_mariano(a.loc[idx].to_numpy(), b.loc[idx].to_numpy(), horizon)[1]


def _lira(r: pd.DataFrame) -> pd.DataFrame:
    # calm/crisis dm_p are approximate: the subsets have non-consecutive origins.
    crisis = r["target_month"].map(is_lira_crisis)
    parts = {"all": r, "calm": r[~crisis], "crisis": r[crisis]}
    rows = []
    for period, sub in parts.items():
        if sub.empty:
            continue
        s = score_relative(sub).reset_index()
        for rec in s.itertuples():
            rows.append((rec.method, rec.horizon, period, rec.mape_ratio, rec.mae_ratio,
                         _dm_p(sub, rec.method, rec.horizon)))
    cols = ["method", "horizon", "period", "mape_ratio", "mae_ratio", "dm_p"]
    return pd.DataFrame(rows, columns=cols)


def _crop_check(r: pd.DataFrame, methods: Mapping[str, tuple[str, str]]) -> pd.DataFrame:
    """``methods``: backtest method -> (method shown, crop-estimate source)."""
    s = score(r).reset_index()
    s = s[s["method"].isin(methods)].copy()
    s["crop_source"] = s["method"].map(lambda m: methods[m][1])
    s["method"] = s["method"].map(lambda m: methods[m][0])
    s["ratio"] = 1 - s["skill"]
    return s[["method", "horizon", "crop_source", "ratio"]]


def _forecast_3m(dev: pd.DataFrame) -> pd.DataFrame | None:
    h3 = dev[dev["horizon"] == 3]
    others = h3[h3["method"] != "naive"]
    if others.empty or h3[h3["method"] == "naive"].empty:
        return None
    mae = (others["forecast"] - others["actual"]).abs().groupby(others["method"]).mean()
    best = mae.idxmin()
    naive = h3[h3["method"] == "naive"].set_index("target_month")
    pick = h3[h3["method"] == best].set_index("target_month")
    out = pd.DataFrame({
        "actual": naive["actual"], "naive": naive["forecast"],
        "best_other": pick["forecast"],
    }).dropna().sort_index()
    out["best_other_method"] = best
    out.index = out.index.astype(str)
    return out.rename_axis("target_month").reset_index()


def _range_band_3m(ranges: pd.DataFrame) -> pd.DataFrame | None:
    r = ranges[(ranges["method"] == "naive_emp") & (ranges["horizon"] == 3)]
    if r.empty:
        return None
    r = r.sort_values("target_month")
    out = r[["target_month", "actual", "q10", "q90"]].copy()
    out["target_month"] = out["target_month"].astype(str)
    return out


def build_results(
    backtest_dir: Path, out_dir: Path, crop_check_methods: Mapping[str, tuple[str, str]] | None = None
) -> list[str]:
    """Write the results tables into ``out_dir``; return the file names written.

    ``crop_check_methods`` (the crop module's ``CROP_CHECK_METHODS``) maps each crop-estimate
    check method to (method shown, crop-estimate source); without it there is no crop check.
    """
    backtest_dir, out_dir = Path(backtest_dir), Path(out_dir)
    dev, holdout = _load(backtest_dir / "dev"), _load(backtest_dir / "holdout")
    lira, ranges = _load(backtest_dir / "dev_try"), _load(backtest_dir / "dev_ranges")
    late = _load(backtest_dir / "dev_late")

    tables: dict[str, pd.DataFrame | None] = {}
    if not dev.empty:
        tables["scoreboard_dev.csv"] = _board(dev)
        tables["scoreboard_shocks.csv"] = _shocks(dev)
        tables["forecast_3m.csv"] = _forecast_3m(dev)
    if not holdout.empty:
        tables["scoreboard_holdout.csv"] = _board(holdout).assign(note=HOLDOUT_NOTE)
    if not lira.empty:
        tables["lira.csv"] = _lira(lira)
    if not ranges.empty:
        s = score_quantiles(ranges).reset_index()
        tables["ranges.csv"] = s[["method", "horizon", "cov80", "width80", "cov90", "width90", "skill"]]
        tables["range_band_3m.csv"] = _range_band_3m(ranges)
    if not late.empty and crop_check_methods:
        tables["crop_check.csv"] = _crop_check(late, crop_check_methods)

    written = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        if df is None:
            continue
        df.to_csv(out_dir / name, index=False)
        written.append(name)
    return written

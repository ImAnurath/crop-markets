"""Run forecasting methods through the walk-forward backtest and print the score table.

Dev mode (default) uses the data without the last 24 months (the holdout) and writes
reports/backtest/dev/<method>.csv. After running, every CSV in the folder is scored together,
so methods run at different times appear in one table.

Usage:
    python scripts/run_backtest.py METHOD [METHOD ...]
    python scripts/run_backtest.py naive seasonal_naive
    python scripts/run_backtest.py season_reg --seasons   # also print the season-level table
    python scripts/run_backtest.py naive lightgbm --holdout   # score the holdout, once

Holdout mode (--holdout) runs on the full data, from 6 months before the holdout so every
horizon is scored on every holdout month, keeps only target months inside the holdout, and
writes reports/backtest/holdout/<method>.csv. The holdout is meant to be scored once: the
script refuses to overwrite an existing holdout file unless --force is given.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from hazelnut.forecast.backtest import holdout_start, run_backtest, split_dev
from hazelnut.forecast.dataset import HORIZONS, load_dataset
from hazelnut.forecast.methods import REGISTRY
from hazelnut.forecast.methods.gbm import Gbm, importances
from hazelnut.forecast.methods.season import season_backtest, season_of
from hazelnut.forecast.metrics import score, score_by_period

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "backtest"
PERIOD_COLUMNS = ("origin", "target_month")


def check_holdout_guard(path: Path, force: bool) -> None:
    """Refuse to score the holdout a second time for the same method."""
    if path.exists() and not force:
        print(
            f"holdout already scored for {path.stem}; it is meant to be scored once "
            "(use --force to override)",
            file=sys.stderr,
        )
        raise SystemExit(1)


def save_results(results: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = results.copy()
    for col in PERIOD_COLUMNS:
        out[col] = out[col].astype(str)
    out.to_csv(path, index=False)


def load_results(folder: Path) -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in sorted(folder.glob("*.csv"))]
    if not frames:
        return pd.DataFrame()
    results = pd.concat(frames, ignore_index=True)
    for col in PERIOD_COLUMNS:
        results[col] = pd.PeriodIndex(results[col], freq="M")
    results["fallback"] = results["fallback"].astype(bool)
    return results


def print_scores(results: pd.DataFrame) -> None:
    pd.set_option("display.width", 140)
    pd.set_option("display.max_rows", 200)
    fmt = {"mae": "{:.3f}", "mape": "{:.1f}", "skill": "{:+.3f}", "fallback_share": "{:.2f}"}
    for title, table in (("All months", score(results)), ("Calm vs shock", score_by_period(results))):
        shown = table.copy()
        for col, f in fmt.items():
            shown[col] = shown[col].map(lambda v, f=f: "" if pd.isna(v) else f.format(v))
        print(f"\n== {title} ==")
        print(shown.to_string())


def print_seasons(target: pd.Series, inputs: pd.DataFrame, first_season: int = 2005) -> None:
    table = season_backtest(target, inputs, first_season=first_season)
    print("\n== Season-ahead regression, one forecast per August (USD/kg) ==")
    print(table.round(3).to_string(index=False))
    scored = table.dropna()
    print(f"\nseasons scored: {len(scored)}")
    for col in ("forecast", "naive_last_season", "naive_august"):
        mae = (scored[col] - scored["actual"]).abs().mean()
        mape = 100 * ((scored[col] - scored["actual"]).abs() / scored["actual"]).mean()
        print(f"  {col:<18} MAE {mae:.3f}  MAPE {mape:.1f}%")


def print_importances(target: pd.Series, inputs: pd.DataFrame) -> None:
    """Top features by gain for LightGBM fitted at the last origin of the data given."""
    model = Gbm()
    model.forecast(target, inputs, list(HORIZONS))
    print(f"\n== LightGBM top features by gain, fitted at {target.index[-1]} ==")
    table = pd.DataFrame(
        {f"h={h}": importances(m).index for h, m in sorted(model.models.items())},
        index=range(1, 9),
    )
    print(table.to_string())


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("methods", nargs="*", choices=sorted(REGISTRY))
    parser.add_argument("--seasons", action="store_true", help="print the season-level table")
    parser.add_argument("--holdout", action="store_true", help="score the final holdout (once)")
    parser.add_argument("--force", action="store_true", help="allow re-scoring the holdout")
    args = parser.parse_args(argv)

    target, inputs = load_dataset()
    if args.holdout:
        folder = OUT / "holdout"
        start_month = holdout_start(target)
        first_origin, score_from = start_month - 6, start_month
        for name in args.methods:  # check every method before running any
            check_holdout_guard(folder / f"{name}.csv", args.force)
        print(f"HOLDOUT: target months {start_month} to {target.index[-1]}")
    else:
        folder = OUT / "dev"
        target, inputs = split_dev(target, inputs)
        first_origin, score_from = None, None
        print(f"dev data: {target.index[0]} to {target.index[-1]} ({len(target)} months)")

    for name in args.methods:
        start = time.perf_counter()
        kwargs = {} if first_origin is None else {"first_origin": first_origin, "score_from": score_from}
        results = run_backtest(REGISTRY[name](), target, inputs, **kwargs)
        save_results(results, folder / f"{name}.csv")
        print(f"{name}: {len(results)} rows in {time.perf_counter() - start:.1f}s")

    print_scores(load_results(folder))
    if args.seasons:
        if args.holdout:
            print_seasons(target, inputs, first_season=season_of(holdout_start(target)))
        else:
            print_seasons(target, inputs)
    if "lightgbm" in args.methods and not args.holdout:
        print_importances(target, inputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

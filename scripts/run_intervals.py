"""Run range (quantile) methods through the walk-forward backtest, on the dev period only.

Writes reports/backtest/dev_ranges/<method>.csv, then scores every CSV in that folder together:
coverage and width of the 80% and 90% intervals, interval score and pinball loss, overall and
split into calm vs shock months. There is deliberately no holdout mode.

Usage:
    python scripts/run_intervals.py METHOD [METHOD ...]
    python scripts/run_intervals.py naive_emp naive_vol sarima
    python scripts/run_intervals.py --figure naive_vol   # 3-month 80% band vs actual price
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from hazelnut.forecast.backtest import split_dev
from hazelnut.forecast.dataset import SHOCK_PERIODS, load_dataset
from hazelnut.forecast.intervals import run_quantile_backtest
from hazelnut.forecast.methods import QUANTILE_REGISTRY
from hazelnut.forecast.metrics import score_quantiles, score_quantiles_by_period

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "reports" / "backtest" / "dev_ranges"
FIGURE = ROOT / "reports" / "figures" / "12_range_3m_band.png"
PERIOD_COLUMNS = ("origin", "target_month")


def save_results(results: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = results.copy()
    for col in PERIOD_COLUMNS:
        out[col] = out[col].astype(str)
    out.to_csv(path, index=False)


def load_results(folder: Path = FOLDER) -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in sorted(folder.glob("*.csv"))]
    if not frames:
        return pd.DataFrame()
    results = pd.concat(frames, ignore_index=True)
    for col in PERIOD_COLUMNS:
        results[col] = pd.PeriodIndex(results[col], freq="M")
    results["fallback"] = results["fallback"].astype(bool)
    return results


def print_scores(results: pd.DataFrame) -> None:
    pd.set_option("display.width", 160)
    pd.set_option("display.max_rows", 200)
    fmt = {c: "{:.2f}" for c in ("cov80", "cov90", "width80", "width90", "is80", "is90")}
    fmt |= {"pinball": "{:.4f}", "skill": "{:+.3f}", "fallback_share": "{:.2f}"}
    for title, table in (
        ("All months", score_quantiles(results)),
        ("Calm vs shock", score_quantiles_by_period(results)),
    ):
        shown = table.copy()
        for col, f in fmt.items():
            shown[col] = shown[col].map(lambda v, f=f: "" if pd.isna(v) else f.format(v))
        print(f"\n== {title} (skill = pinball vs naive_emp) ==")
        print(shown.to_string())


def plot_band(results: pd.DataFrame, method: str, target: pd.Series, horizon: int = 3) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    INK, MUTED, GRID, BAND = "#2b2b29", "#6b6a63", "#e4e3dd", "#2a78d6"
    r = results[(results["method"] == method) & (results["horizon"] == horizon)]
    r = r.sort_values("target_month")
    x = r["target_month"].dt.to_timestamp()
    miss = (r["actual"] < r["q10"]) | (r["actual"] > r["q90"])

    fig, ax = plt.subplots(figsize=(11, 4.5))
    for a, b in SHOCK_PERIODS:
        if pd.Period(a, "M") <= r["target_month"].max():
            ax.axvspan(pd.Period(a, "M").to_timestamp(), (pd.Period(b, "M") + 1).to_timestamp(),
                       color=GRID, alpha=0.6, lw=0)
    ax.fill_between(x, r["q10"], r["q90"], color=BAND, alpha=0.25, lw=0,
                    label=f"80% range made {horizon} months earlier")
    ax.plot(x, r["actual"], color=INK, lw=1.6, label="Actual monthly price")
    ax.scatter(x[miss], r.loc[miss, "actual"], s=14, color=INK, zorder=3,
               label=f"Outside the range ({miss.mean():.0%} of months)")
    cov = 1 - miss.mean()
    ax.set_title(f"{method}: {horizon}-month-ahead 80% range vs actual Giresun price "
                 f"(dev period, coverage {cov:.0%}; shaded = shock periods)",
                 loc="left", color=INK, fontsize=11)
    ax.set_ylabel("USD/kg", color=INK)
    ax.grid(True, color=GRID)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED)
    ax.legend(loc="upper left", frameon=False)
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=110)
    plt.close(fig)
    return FIGURE


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("methods", nargs="*", choices=sorted(QUANTILE_REGISTRY))
    parser.add_argument("--figure", choices=sorted(QUANTILE_REGISTRY), help="plot this method's band")
    args = parser.parse_args(argv)

    target, inputs = split_dev(*load_dataset())
    print(f"dev data: {target.index[0]} to {target.index[-1]} ({len(target)} months)")
    for name in args.methods:
        start = time.perf_counter()
        results = run_quantile_backtest(QUANTILE_REGISTRY[name](), target, inputs)
        save_results(results, FOLDER / f"{name}.csv")
        print(f"{name}: {len(results)} rows in {time.perf_counter() - start:.1f}s")

    results = load_results()
    if not results.empty:
        print_scores(results)
    if args.figure:
        print(f"\nfigure: {plot_band(results, args.figure, target)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

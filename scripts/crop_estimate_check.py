"""Crop-estimate checks on the development period (never the holdout).

1. Season level: the season regression with the Giresun estimate vs the national estimate.
2. Timing sensitivity: rerun the monthly methods that use a crop input with every crop
   estimate made visible one month later (September instead of August), and the 2018
   Giresun estimate held back to November 2018 like the national one (no public 2018
   Ministry estimate was found before October 2018). If the scores barely move, the
   exact publication month does not drive the results.

Writes reports/backtest/dev_late/<method>.csv and prints MAE / naive MAE per horizon for
the standard inputs (reports/backtest/dev, run scripts/run_backtest.py first) and the late ones.

Usage:
    python scripts/crop_estimate_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_backtest import OUT, load_results, save_results  # noqa: E402

from hazelnut.forecast.backtest import run_backtest, split_dev  # noqa: E402
from hazelnut.forecast.dataset import load_dataset  # noqa: E402
from hazelnut.forecast.methods import REGISTRY  # noqa: E402
from hazelnut.forecast.methods.season import season_backtest  # noqa: E402
from hazelnut.forecast.metrics import score  # noqa: E402

LATE_METHODS = ["naive", "sarimax", "lightgbm", "sarimax_nat", "lightgbm_nat"]
GIRESUN_COLS = ["crop_estimate_t", "crop_change"]
NATIONAL_COLS = ["nat_crop_estimate_t", "nat_crop_change"]


def late_inputs(inputs: pd.DataFrame) -> pd.DataFrame:
    """Every crop column one month later; the 2018 Giresun estimate held back to November."""
    late = inputs.copy()
    for col in GIRESUN_COLS + NATIONAL_COLS:
        late[col] = inputs[col].shift(1)
    for col in GIRESUN_COLS:
        late.loc[pd.Period("2018-09", "M"):pd.Period("2018-10", "M"), col] = late.at[
            pd.Period("2018-08", "M"), col
        ]
    return late


def ratio_table(folder: Path) -> pd.DataFrame:
    s = score(load_results(folder))
    return (1 - s["skill"]).unstack("horizon").round(3).add_prefix("h=")


def season_table(target: pd.Series, inputs: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for col in ("crop_change", "nat_crop_change"):
        t = season_backtest(target, inputs, crop_col=col).dropna()
        rows[f"season_reg[{col}]"] = ((t["forecast"] - t["actual"]).abs().mean(), len(t))
    rows["naive_last_season"] = ((t["naive_last_season"] - t["actual"]).abs().mean(), len(t))
    rows["naive_august"] = ((t["naive_august"] - t["actual"]).abs().mean(), len(t))
    return pd.DataFrame(rows, index=["MAE USD/kg", "seasons"]).T.round(3)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    target, inputs = split_dev(*load_dataset())
    print("== Season level (one forecast per August) ==")
    print(season_table(target, inputs).to_string())

    late = late_inputs(inputs)
    folder = OUT / "dev_late"
    for name in LATE_METHODS:
        save_results(run_backtest(REGISTRY[name](), target, late), folder / f"{name}.csv")
    print("\n== MAE / naive MAE, standard timing (reports/backtest/dev) ==")
    print(ratio_table(OUT / "dev").to_string())
    print("\n== MAE / naive MAE, crop estimates one month later ==")
    print(ratio_table(folder).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

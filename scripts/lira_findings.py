"""Numbers behind reports/lira_forecast_findings.md (development period only).

Reads reports/backtest/dev_try/*.csv (written by ``run_backtest.py --currency try ...``) and
prints: the drift-window choice (made on target months up to 2014-12 only), MAPE ratios by era,
Diebold-Mariano tests vs lira naive, and an FX-oracle bound (USD naive x the realised FX).

Usage: python scripts/lira_findings.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from hazelnut.forecast.backtest import split_dev
from hazelnut.forecast.dataset import load_dataset_try
from hazelnut.forecast.metrics import diebold_mariano, score_relative

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "reports" / "backtest" / "dev_try"
CHOICE_END = pd.Period("2014-12", "M")
ERAS = {"2005-17": ("2005-01", "2017-12"), "2018-24": ("2018-01", "2024-09")}


def load() -> pd.DataFrame:
    r = pd.concat([pd.read_csv(p) for p in sorted(FOLDER.glob("*.csv"))], ignore_index=True)
    for col in ("origin", "target_month"):
        r[col] = pd.PeriodIndex(r[col], freq="M")
    r["fallback"] = r["fallback"].astype(bool)
    return r


def mape_ratio(r: pd.DataFrame) -> pd.Series:
    return score_relative(r)["mape_ratio"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    r = load()
    pd.set_option("display.width", 160)

    print("== Window choice: mean MAPE ratio over h=1,3,6, target months <= 2014-12 ==")
    early = mape_ratio(r[r["target_month"] <= CHOICE_END]).groupby(level="method").mean()
    print(early.round(3).sort_values().to_string())

    print("\n== MAPE ratio vs lira naive by era (target month) ==")
    eras = {}
    for name, (a, b) in ERAS.items():
        m = r["target_month"].between(pd.Period(a, "M"), pd.Period(b, "M"))
        eras[name] = mape_ratio(r[m])
    print(pd.DataFrame(eras).unstack("horizon").round(3).to_string())

    print("\n== Diebold-Mariano vs naive, loss = |log error| (stat < 0: method better) ==")
    r = r.assign(loss=np.abs(np.log(r["forecast"] / r["actual"])))
    base = r[r["method"] == "naive"].set_index(["origin", "horizon"])["loss"]
    rows = []
    for (method, h), g in r[r["method"] != "naive"].groupby(["method", "horizon"]):
        g = g.set_index(["origin", "horizon"])
        stat, p = diebold_mariano(g["loss"].to_numpy(), base.loc[g.index].to_numpy(), h)
        rows.append((method, h, round(stat, 2), round(p, 3)))
    print(pd.DataFrame(rows, columns=["method", "h", "dm", "p"]).pivot(
        index="method", columns="h", values=["dm", "p"]).to_string())

    print("\n== FX oracle: USD naive x realised USD/TRY of the target month (not a forecast) ==")
    target, inputs = split_dev(*load_dataset_try())
    fx = inputs["usd_try"]
    naive = r[r["method"] == "naive"].copy()
    usd_last = naive["forecast"].to_numpy() / fx.loc[naive["origin"]].to_numpy()
    naive["forecast"] = usd_last * fx.loc[naive["target_month"]].to_numpy()
    naive["method"] = "fx_oracle"
    print(score_relative(pd.concat([r[r["method"] == "naive"], naive]))[
        ["mape", "mape_ratio", "mae_ratio"]].round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

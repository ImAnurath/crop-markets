# %% [markdown]
# # Forecast comparison
#
# Every method was run through the same walk-forward backtest (scripts/run_backtest.py):
# at each month from 2005-01 it saw only what was known at the end of that month and
# forecast the Giresun price 1, 3 and 6 months ahead. This notebook scores those forecasts,
# side by side, against the naive "next month = this month" baseline.
#
# Run cell by cell in VS Code (the `# %%` markers), or the whole file with
# `python notebooks/02_forecast_comparison.py`. Figures go to reports/figures/ and the
# write-up to reports/forecast_results.md.

# %%
from pathlib import Path

import matplotlib

if __name__ == "__main__":
    matplotlib.use("Agg")  # running as a script: save figures, don't open windows
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hazelnut.forecast.backtest import split_dev
from hazelnut.forecast.dataset import HORIZONS, load_dataset
from hazelnut.forecast.methods.season import season_backtest
from hazelnut.forecast.metrics import score, score_by_period

ROOT = Path(__file__).resolve().parent.parent if "__file__" in globals() else Path.cwd()
BACKTEST = ROOT / "reports" / "backtest"
FIG = ROOT / "reports" / "figures"
REPORT = ROOT / "reports" / "forecast_results.md"
FIG.mkdir(parents=True, exist_ok=True)

INK, MUTED, GRID = "#2b2b29", "#6b6a63", "#e4e3dd"
HORIZON_COLORS = {1: "#2a78d6", 3: "#eb6834", 6: "#1baf7a"}  # validated categorical slots 1-3
plt.rcParams.update({
    "figure.figsize": (11, 4.5), "axes.grid": True, "grid.color": GRID, "grid.alpha": 1.0,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
})

# Order in every table and chart: baselines first, then the methods in the order they were built.
ORDER = ["naive", "seasonal_naive", "sarima", "sarimax", "season_reg", "lightgbm", "chronos"]
LABELS = {
    "naive": "Naive", "seasonal_naive": "Seasonal naive", "sarima": "SARIMA",
    "sarimax": "SARIMAX", "season_reg": "Season regression", "lightgbm": "LightGBM",
    "chronos": "Chronos-Bolt",
}


def savefig(name: str) -> str:
    plt.tight_layout()
    plt.savefig(FIG / f"{name}.png", dpi=110)
    plt.close()
    return f"reports/figures/{name}.png"


def load_results(folder: Path) -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in sorted(folder.glob("*.csv"))]
    if not frames:
        return pd.DataFrame()
    r = pd.concat(frames, ignore_index=True)
    for col in ("origin", "target_month"):
        r[col] = pd.PeriodIndex(r[col], freq="M")
    r["fallback"] = r["fallback"].astype(bool)
    return r


def ordered(table: pd.DataFrame) -> pd.DataFrame:
    present = [m for m in ORDER if m in table.index.get_level_values("method")]
    return table.reindex(present, level="method")


def wide(table: pd.DataFrame) -> pd.DataFrame:
    """method x (metric, horizon) with rounded, readable columns."""
    t = ordered(table)[["mae", "mape", "skill", "fallback_share"]].unstack("horizon")
    t = t.reindex([m for m in ORDER if m in t.index])
    t.index = [LABELS[m] for m in t.index]
    names = {"mae": "MAE", "mape": "MAPE %", "skill": "Skill", "fallback_share": "Fallback"}
    t.columns = [f"{names[metric]} h={h}" for metric, h in t.columns]
    decimals = {"MAE": 3, "MAPE %": 1, "Skill": 3, "Fallback": 2}
    for col in t.columns:
        t[col] = t[col].round(decimals[col.split(" h=")[0]])
    return t


md: list[str] = []  # the markdown report, built up section by section

dev = load_results(BACKTEST / "dev")
holdout = load_results(BACKTEST / "holdout")
target, inputs = load_dataset()
dev_target, dev_inputs = split_dev(target, inputs)
print(f"dev results: {len(dev):,} rows, methods: {sorted(dev.method.unique())}")
print(f"holdout results: {len(holdout):,} rows")

# %% [markdown]
# ## 1. Score table (development period)
# MAE in USD/kg, MAPE in percent. Skill = 1 - MAE / naive MAE on the same forecasts:
# above 0 beats naive, below 0 loses to it. Fallback = share of forecasts where the method
# had nothing to say and the naive forecast was used instead.

# %%
dev_scores = score(dev)
dev_wide = wide(dev_scores)
print(dev_wide.to_string())
first, last = dev.target_month.min(), dev.target_month.max()
n_origins = dev.origin.nunique()

# %% [markdown]
# ## 2. Calm vs shock periods
# Shock periods (by target month): 2005, 2014-15 and 2025. Averages hide where a method
# fails, so the same scores are split.

# %%
by_period = ordered(score_by_period(dev))
period_table = by_period[["n", "mae", "skill"]].unstack("period")
period_table.columns = [f"{m.upper() if m == 'mae' else m.capitalize()} {p}" for m, p in period_table.columns]
period_table = period_table.reindex(
    pd.MultiIndex.from_tuples([(m, h) for m in ORDER for h in HORIZONS if (m, h) in period_table.index])
)
period_table.index = [f"{LABELS[m]}, h={h}" for m, h in period_table.index]
period_table = period_table.round({c: 3 for c in period_table.columns if not c.startswith("N")})
print(period_table.to_string())

# %% [markdown]
# ## 3. Skill vs naive, by horizon

# %%
skill = ordered(dev_scores)["skill"].unstack("horizon")
methods = [m for m in ORDER if m in skill.index and m != "naive"]
CLIP = -0.7
fig, ax = plt.subplots(figsize=(10, 5.5))
bar_h = 0.26
for i, h in enumerate(HORIZONS):
    y = np.arange(len(methods)) + (i - 1) * (bar_h + 0.02)
    values = skill.loc[methods, h].to_numpy()
    ax.barh(y, np.maximum(values, CLIP), height=bar_h, color=HORIZON_COLORS[h], label=f"{h} month{'s' if h > 1 else ''} ahead")
    for yy, v in zip(y, values):
        if v < CLIP:
            ax.text(CLIP + 0.01, yy, f"{v:+.2f} (cut off)", va="center", ha="left", fontsize=8, color="white")
ax.axvline(0, color=INK, linewidth=1)
ax.set_yticks(np.arange(len(methods)), [LABELS[m] for m in methods])
ax.invert_yaxis()
ax.set_xlim(CLIP, 0.1)
ax.set_xlabel("Skill vs naive (0 = as good as naive; below 0 = worse)")
ax.set_title("No method beats \"next month = this month\" on the development period", loc="left", color=INK)
ax.legend(loc="lower left", frameon=False)
ax.grid(axis="y", visible=False)
fig_skill = savefig("10_skill_vs_naive")

# %% [markdown]
# ## 4. What the 3-month-ahead forecasts look like
# One small panel per method: the actual price and the forecast made 3 months earlier.

# %%
actual = dev_target.loc["2005-01":]
panels = [m for m in ORDER if m in dev.method.unique()]
cols = 2
rows = int(np.ceil(len(panels) / cols))
fig, axes = plt.subplots(rows, cols, figsize=(12, 2.4 * rows), sharex=True, sharey=True)
for ax, m in zip(axes.flat, panels):
    f = dev[(dev.method == m) & (dev.horizon == 3)].set_index("target_month")["forecast"].sort_index()
    ax.plot(actual.index.to_timestamp(), actual.to_numpy(), color=MUTED, linewidth=1.5, label="Actual")
    ax.plot(f.index.to_timestamp(), f.to_numpy(), color=HORIZON_COLORS[1], linewidth=1.5, label="Forecast made 3 months earlier")
    ax.set_title(LABELS[m], loc="left", fontsize=10, color=INK)
for ax in list(axes.flat)[len(panels):]:
    ax.set_visible(False)
axes.flat[0].legend(loc="upper left", frameon=False, fontsize=8)
fig.supylabel("USD/kg", color=INK)
fig_paths = savefig("11_forecast_3m_vs_actual")

# %% [markdown]
# ## 5. Season-ahead regression at season level
# One forecast per August for the coming season's average price (September to August),
# against two simple guesses: last season's average, and the August price itself.
# Only about 19 seasons, so treat the differences as indicative.

# %%
seasons = season_backtest(dev_target, dev_inputs)
scored_seasons = seasons.dropna()
season_mae = pd.DataFrame({
    "MAE": [(scored_seasons[c] - scored_seasons.actual).abs().mean() for c in ("forecast", "naive_last_season", "naive_august")],
    "MAPE %": [100 * ((scored_seasons[c] - scored_seasons.actual).abs() / scored_seasons.actual).mean()
               for c in ("forecast", "naive_last_season", "naive_august")],
}, index=["Season regression", "Last season's average", "August price"]).round({"MAE": 3, "MAPE %": 1})
print(seasons.round(3).to_string(index=False))
print(season_mae.to_string())

# %% [markdown]
# ## 6. Final holdout (scored once)
# The last 24 months were kept out of all development work and scored once at the end.

# %%
holdout_wide = None
if len(holdout):
    hold_scores = score(holdout)
    holdout_wide = wide(hold_scores)
    both = pd.concat(
        {"Dev": ordered(dev_scores)[["mae", "skill"]], "Holdout": ordered(hold_scores)[["mae", "skill"]]},
        axis=1,
    )
    both = both.reindex([(m, h) for m in ORDER for h in HORIZONS if (m, h) in both.index])
    both.index = [f"{LABELS[m]}, h={h}" for m, h in both.index]
    both.columns = [f"{p} {c.upper() if c == 'mae' else c}" for p, c in both.columns]
    dev_vs_holdout = both.round(3)
    print(holdout_wide.to_string())
    print(dev_vs_holdout.to_string())
    hold_first, hold_last = holdout.target_month.min(), holdout.target_month.max()
else:
    print("no holdout results yet")

# %% [markdown]
# ## Write the report

# %%
# Plain-language summaries, written after looking at the numbers above.
SUMMARY_DEV = """\
- **Nothing beats naive.** Over {n_origins} monthly forecast origins (target months {first} to {last}),
  no method improves on "next month's price = this month's price" at any horizon. The
  closest challengers (seasonal naive and SARIMA) lose to it by 2-4%.
  That is the honest headline: the Giresun USD price behaves close to a random walk at
  1-6 months.
- **Outside inputs did not help.** SARIMAX (with crop estimate and exchange-rate changes)
  is no better than SARIMA without them, and worse at 1 month. LightGBM with every input
  is worse than naive by 5-13%, and Chronos-Bolt (zero-shot, price only) by 6-8%.
- **Shocks are where everyone fails.** In the 2005 and 2014-15 shock periods, errors are
  2 to 2.7 times their calm-period size for every month-to-month method, naive included.
  (The season regression's errors grow less because they are already large in calm months.)
  Beating naive during shocks is rare and small: seasonal naive at 1 and 6 months (+2 to +4%)
  and the season regression at 6 months (+6%).
- **The season regression is a different tool.** Used as a monthly forecast it is far worse
  than naive (it predicts one season average for every month). At season level it beats
  "same as last season" (MAE {season_reg:.2f} vs {last_season:.2f} USD/kg) but is about level
  with simply taking the August price ({august:.2f}), on only {n_seasons} seasons.
"""

SUMMARY_HOLDOUT = """\
- **Only 24 forecasts per horizon**, half of them in the 2025 price spike, so one or two
  big misses move every number here. Read it as a sanity check, not a new ranking.
- **Still no consistent winner over naive.** Some methods edge ahead at one horizon:
  SARIMA (+5%) and LightGBM (+5%) at 1 month, the season regression (+18%) at 6 months.
  Each of them loses at another horizon (LightGBM by 22% at 6 months), and none of them
  beat naive on the development period.
- **The 6-month season-regression gain is small-sample luck as much as skill.** 42% of its
  6-month forecasts were naive fallbacks, and the gain comes from the calm months (late 2024
  and 2026), not the 2025 spike. At
  season level it again sits next to "take the August price" (2 seasons only).
- **The development-period conclusion stands.** At 1-6 months this price is very hard to beat
  with "it stays where it is". A model is worth using only if it beats naive on both periods,
  and none does.
"""

md.append("# Hazelnut price forecasting: results\n")
md.append(
    "Target: Giresun Commodity Exchange monthly average in-shell hazelnut price, USD/kg. "
    "Forecasts 1, 3 and 6 months ahead, from a walk-forward backtest where each forecast "
    "uses only information available at the time. Code: `src/hazelnut/forecast/`, "
    "runs: `scripts/run_backtest.py`, this report: `notebooks/02_forecast_comparison.py`.\n"
)
md.append("## Summary (development period)\n")
md.append(SUMMARY_DEV.format(
    n_origins=n_origins, first=first, last=last,
    season_reg=season_mae.loc["Season regression", "MAE"],
    last_season=season_mae.loc["Last season's average", "MAE"],
    august=season_mae.loc["August price", "MAE"], n_seasons=len(scored_seasons),
))
if holdout_wide is not None:
    md.append(f"## Summary (final holdout, {hold_first} to {hold_last})\n")
    md.append(SUMMARY_HOLDOUT or "_Holdout scored; summary pending._\n")
md.append(f"## Scores, development period (target months {first} to {last})\n")
md.append("MAE in USD/kg, MAPE in %, skill = 1 - MAE / naive MAE (above 0 beats naive), "
          "fallback = share of forecasts where the method declined and naive was used.\n")
md.append(dev_wide.to_markdown() + "\n")
md.append(f"![Skill vs naive](figures/{Path(fig_skill).name})\n")
md.append("## Calm vs shock periods\n")
md.append("Shock periods by target month: 2005, 2014-2015, 2025.\n")
md.append(period_table.to_markdown() + "\n")
md.append("## Season-ahead regression, season level\n")
md.append("One forecast per August for the average price of the coming September-August season. "
          f"{len(scored_seasons)} seasons: a small sample.\n")
md.append(season_mae.to_markdown() + "\n")
md.append(seasons.round(3).to_markdown(index=False) + "\n")
md.append("## 3-month-ahead forecasts vs actual\n")
md.append(f"![3-month-ahead forecasts vs actual](figures/{Path(fig_paths).name})\n")
if holdout_wide is not None:
    md.append(f"## Scores, final holdout (target months {hold_first} to {hold_last}, scored once)\n")
    md.append(holdout_wide.to_markdown() + "\n")
    md.append("### Dev vs holdout\n")
    md.append(dev_vs_holdout.to_markdown() + "\n")
md.append("## Method notes\n")
md.append(
    "- **Naive**: last observed price. **Seasonal naive**: last price times the average past "
    "change between this calendar month and the target month.\n"
    "- **SARIMA / SARIMAX**: seasonal ARIMA on log price with drift; order picked by AIC on "
    "training data once a year; SARIMAX adds crop-estimate change and USD/TRY change.\n"
    "- **Season regression**: each August, log change of the season average regressed on the "
    "log change of the Giresun crop estimate.\n"
    "- **LightGBM**: one model per horizon on price lags, month, crop, frost, exports, FX and "
    "volume features; fixed parameters, refit every month.\n"
    "- **Chronos-Bolt (small)**: pretrained forecaster, zero-shot on the price history only.\n"
)
REPORT.write_text("\n".join(md), encoding="utf-8")
print(f"wrote {REPORT.relative_to(ROOT)}")

# %% [markdown]
# # First look at the data
#
# Goal: see what each source looks like, how much of it there is, and whether the sources
# agree with each other. No modelling yet.
#
# Run cell by cell in VS Code (the `# %%` markers), or the whole file with
# `python notebooks/01_first_look.py`. Figures go to reports/figures/.

# %%
from pathlib import Path

import matplotlib

if __name__ == "__main__":
    matplotlib.use("Agg")  # running as a script: save figures, don't open windows
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent if "__file__" in globals() else Path.cwd()
DATA = ROOT / "data" / "interim"
FIG = ROOT / "reports" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"figure.figsize": (11, 4.5), "axes.grid": True, "grid.alpha": 0.3})


def savefig(name: str) -> None:
    plt.tight_layout()
    plt.savefig(FIG / f"{name}.png", dpi=110)
    plt.close()


# %% [markdown]
# ## Load and put everything in today's lira
# Before 2005 Turkey used old lira; 1 new lira = 1,000,000 old lira.

# %%
ordu = pd.read_csv(DATA / "ordu_daily.csv", parse_dates=["date"])
ordu.loc[ordu.old_lira, "price"] /= 1_000_000

gir = pd.read_csv(DATA / "giresun_monthly_price.csv")
for col in ["usd_try", "price_min_try", "price_max_try", "price_avg_try"]:
    gir.loc[gir.old_lira, col] /= 1_000_000
gir["date"] = pd.to_datetime(dict(year=gir.year, month=gir.month, day=1))
# The monthly average only starts in later years; the min/max midpoint covers all of it.
gir["price_mid_try"] = (gir.price_min_try + gir.price_max_try) / 2
gir["price_mid_usd"] = (gir.price_min_usd + gir.price_max_usd) / 2

tobb = pd.read_csv(DATA / "tobb_daily.csv", parse_dates=["date"])
cpi = pd.read_csv(DATA / "cpi_monthly.csv")
cpi["date"] = pd.to_datetime(cpi.month)
fx = pd.read_csv(DATA / "fx_daily.csv", parse_dates=["date"])

print("Ordu daily:", ordu.date.min().date(), "to", ordu.date.max().date(), f"({len(ordu):,} days)")
print("Giresun monthly:", gir.date.min().date(), "to", gir.date.max().date(),
      f"({gir.price_avg_try.notna().sum()} months with an average, {len(gir)} with min/max)")
print("TOBB:", tobb.date.min().date(), "to", tobb.date.max().date(), f"({len(tobb):,} rows)")

# %% [markdown]
# ## 1. The price over time, three ways
# Nominal lira is dominated by inflation, so we also look at USD and at inflation-adjusted lira.

# %%
cpi_m = cpi.set_index("date")["cpi"]
latest_cpi = cpi_m.iloc[-1]
gir_m = gir.set_index("date")
gir_m["price_real_try"] = gir_m.price_mid_try * latest_cpi / cpi_m.reindex(gir_m.index)

fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)
gir_m.price_mid_try.plot(ax=axes[0], logy=True, title="Giresun monthly price, nominal TL/kg (log scale)")
gir_m.price_mid_usd.plot(ax=axes[1], color="tab:green", title="Same price in USD/kg")
gir_m.price_real_try.plot(ax=axes[2], color="tab:red",
                          title=f"Same price in today's lira (CPI-adjusted to {cpi.month.iloc[-1]})")
savefig("01_price_three_ways")

# %% [markdown]
# ## 2. When does trading happen?
# Days with a price in the Ordu sheet, by month of year and by year.

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
ordu.groupby(ordu.date.dt.month).size().plot.bar(ax=axes[0], title="Ordu trading days by month (all years)")
ordu.groupby(ordu.date.dt.year).size().plot.bar(ax=axes[1], title="Ordu trading days per year")
savefig("02_trading_days")

vol = pd.read_csv(DATA / "giresun_monthly_volume.csv")
by_month = vol.groupby("month").quantity_kg.sum() / vol.quantity_kg.sum() * 100
print("Share of Giresun registered volume by calendar month (%):")
print(by_month.round(1).to_string())

# %% [markdown]
# ## 3. Do the sources agree?
# Ordu sheet vs TOBB's Ordu Levant series on the same days, and Ordu vs Giresun monthly.

# %%
tobb_ordu = tobb[(tobb.exchange == "ordu") & (tobb.grade == "inshell_tombul_levant")]
same_day = ordu.merge(tobb_ordu[["date", "price_avg"]], on="date")
same_day["diff_pct"] = (same_day.price / same_day.price_avg - 1) * 100
print(f"Same-day matches Ordu sheet vs TOBB: {len(same_day)}; "
      f"median gap {same_day.diff_pct.median():.2f}%, "
      f"within 1%: {(same_day.diff_pct.abs() < 1).mean():.0%}")

ordu_m = ordu.set_index("date").price.resample("MS").mean()
both = pd.DataFrame({"ordu": ordu_m, "giresun": gir_m.price_mid_try}).dropna()
both["ratio"] = both.giresun / both.ordu
ax = both.ratio.plot(title="Giresun monthly price / Ordu monthly price (above 1 = Giresun dearer)")
ax.axhline(1, color="black", lw=0.8)
savefig("03_giresun_vs_ordu")
print(f"Giresun/Ordu ratio: median {both.ratio.median():.3f}, months compared {len(both)}")

# %% [markdown]
# ## 4. Crop size vs price
# Turkey's production (FAOSTAT) against the average USD price of the following season.

# %%
fao = pd.read_csv(DATA / "faostat_production.csv")
tr_prod = (fao[(fao.area == "Türkiye") & (fao.element == "Production")]
           .set_index("year").value / 1000).rename("production_kt")
# Season price: average of Sep (harvest) to the next Aug, in USD.
g = gir.copy()
g["season"] = g.year.where(g.month >= 9, g.year - 1)
season_usd = g.groupby("season").price_mid_usd.mean().rename("season_price_usd")
crop = pd.concat([tr_prod, season_usd], axis=1).dropna()
fig, ax = plt.subplots(figsize=(7, 5))
ax.scatter(crop.production_kt, crop.season_price_usd)
for yr, r in crop.iterrows():
    ax.annotate(str(int(yr)), (r.production_kt, r.season_price_usd), fontsize=7)
ax.set(xlabel="Turkey production (thousand t, in shell)", ylabel="Season avg price (USD/kg)",
       title="Bigger crop, cheaper hazelnuts?")
savefig("04_crop_vs_price")
print(f"Correlation production vs season USD price: {crop.corr().iloc[0, 1]:.2f} ({len(crop)} seasons)")

# %% [markdown]
# ## 5. Exports
# Monthly shelled exports (the bulk of the trade), world total and top buyers.

# %%
ct = pd.read_csv(DATA / "comtrade_monthly.csv")
world = ct[ct.partner == "World"].pivot_table(index="month", columns="product", values="net_kg", aggfunc="sum") / 1e6
world.index = pd.to_datetime(world.index)
world.plot(title="Turkey hazelnut exports per month (thousand tonnes)")
savefig("05_exports_monthly")

top = (ct[(ct.partner != "World") & (ct.month >= "2020")].groupby("partner").net_kg.sum()
       .sort_values(ascending=False).head(10) / ct[(ct.partner != "World") & (ct.month >= "2020")].net_kg.sum() * 100)
print("Top destinations since 2020 (% of tonnes):")
print(top.round(1).to_string())

shelled = ct[(ct.partner == "World") & (ct["product"] == "shelled")].copy()
shelled["unit_usd_kg"] = shelled.fob_usd / shelled.net_kg
shelled["date"] = pd.to_datetime(shelled.month)
ax = shelled.set_index("date").unit_usd_kg.plot(label="Export unit value, shelled (USD/kg)")
(gir_m.price_mid_usd * 2).plot(ax=ax, label="Giresun in-shell price x2 (roughly kernel-equivalent)")
ax.set_title("World kernel price vs local in-shell price")
ax.legend()
savefig("06_export_unit_value")

# %% [markdown]
# ## 6. Weather: spring frost
# Frost during flowering and early nut set (March-April) is the classic crop killer.

# %%
w = pd.read_csv(DATA / "weather_daily.csv", parse_dates=["date"])
spring = w[w.date.dt.month.isin([3, 4])]
frost = (spring[spring.temperature_2m_min < 0].groupby([spring.date.dt.year, "location"]).size()
         .unstack(fill_value=0))
frost.plot.bar(stacked=True, figsize=(13, 4.5), title="Frost days (min below 0°C) in March-April")
savefig("07_spring_frost")
print("Years with most spring frost days (all locations summed):")
print(frost.sum(axis=1).sort_values(ascending=False).head(8).to_string())

# %%
print(f"\nFigures saved to {FIG}")

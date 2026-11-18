"""Hazelnut site tables: pure functions from the interim tables to tidy frames.

Months are ``YYYY-MM`` strings; seasons run September to August and are labelled ``2025/26``.
Old-lira (pre-2005) values are rescaled to new lira the same way as ``forecast.dataset``.
Builders never mutate their inputs.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from hazelnut.forecast.dataset import (
    _FILES,
    NATIONAL_CROP_FILE,
    OLD_LIRA_FACTOR,
    frost_feature,
    fx_feature,
    target_series,
    target_series_try,
)
from hazelnut.site.config import REPO_ROOT

# --- Crop hooks read by the shared site layer (site_data, validate, results, scripts) ---

ORDU_FILE = "ordu_daily.csv"
# Input tables: {table key: (folder, file name)}; folder is "interim" or "manual".
INPUT_FILES: dict[str, tuple[str, str]] = {
    **{key: ("interim", name) for key, name in _FILES.items()},
    "ordu_daily": ("interim", ORDU_FILE),
    "national_crop": ("manual", NATIONAL_CROP_FILE),
}
# prices_monthly columns the validation gate checks for gaps and non-positive values.
PRICE_COLUMNS = ("usd_kg", "try_kg", "usd_try")
# crop_by_year column the stat strip shows as the crop estimate: Giresun exchange's estimate.
STATS_CROP_COL = "giresun_estimate_t"
# Comtrade product the destination ranking covers: the bulk of the trade is shelled.
EXPORT_PRODUCT = "shelled"
# Committed backtest results the forecasting tables are scored from (never re-run here).
BACKTEST_DIR = REPO_ROOT / "reports" / "backtest"
# Crop-estimate check: backtest method -> (method shown, whose crop estimate it used).
CROP_CHECK_METHODS = {
    "sarimax": ("sarimax", "giresun"), "lightgbm": ("lightgbm", "giresun"),
    "sarimax_nat": ("sarimax", "national"), "lightgbm_nat": ("lightgbm", "national"),
}


def season_label(month: pd.Period) -> str:
    return _label_of_start(month.year if month.month >= 9 else month.year - 1)


def _season_start(months: pd.PeriodIndex) -> np.ndarray:
    return np.where(np.asarray(months.month) >= 9, np.asarray(months.year), np.asarray(months.year) - 1)


def _label_of_start(start: int) -> str:
    return f"{start}/{(start + 1) % 100:02d}"


def _seasons(months: pd.PeriodIndex) -> list[str]:
    return [_label_of_start(int(s)) for s in _season_start(months)]


def prices_monthly(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    gp = tables["giresun_price"]
    usd = target_series(gp)
    months = usd.index
    out = pd.DataFrame(
        {
            "usd_kg": usd.to_numpy(),
            "try_kg": target_series_try(gp).reindex(months).to_numpy(),
            "usd_try": fx_feature(gp, months).to_numpy(),
        },
        index=months,
    )
    out = out.dropna(subset=["usd_kg", "try_kg"], how="all")
    out.insert(0, "season", _seasons(out.index))
    out.insert(0, "month", out.index.astype(str))
    return out.reset_index(drop=True)


def ordu_monthly(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    daily = tables["ordu_daily"]
    price = daily["price"].astype(float).to_numpy()
    price = np.where(daily["old_lira"].astype(bool).to_numpy(), price / OLD_LIRA_FACTOR, price)
    month = pd.PeriodIndex(pd.to_datetime(daily["date"]).dt.to_period("M"))
    grouped = pd.Series(price, index=month).groupby(level=0)
    months = pd.PeriodIndex(grouped.mean().index)
    try_kg = grouped.mean().to_numpy()
    rate = fx_feature(tables["giresun_price"], months).to_numpy()
    out = pd.DataFrame(
        {"try_kg": try_kg, "usd_kg": try_kg / rate, "trade_days": grouped.size().to_numpy()},
        index=months,
    )
    out.insert(0, "season", _seasons(months))
    out.insert(0, "month", months.astype(str))
    return out.reset_index(drop=True)


def exports_monthly(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    c = tables["comtrade"]
    return c[["month", "product", "partner", "net_kg", "fob_usd"]].reset_index(drop=True)


def _top_product_by_partner(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    c = tables["comtrade"]
    return c[(c["product"] == EXPORT_PRODUCT) & (c["partner"] != "World")]


def exports_top(tables: dict[str, pd.DataFrame], months: int = 12, top: int = 10) -> pd.DataFrame:
    """Shelled exports by partner over the last ``months`` months with data; share is of net_kg."""
    c = _top_product_by_partner(tables)
    recent = sorted(c["month"].unique())[-months:]
    by_partner = (
        c[c["month"].isin(recent)]
        .groupby("partner")[["net_kg", "fob_usd"]]
        .sum()
        .sort_values("net_kg", ascending=False)
    )
    head, rest = by_partner.iloc[:top], by_partner.iloc[top:]
    if len(rest):
        head = pd.concat([head, rest.sum().to_frame("Other").T])
    head = head.assign(share=head["net_kg"] / head["net_kg"].sum())
    return head.rename_axis("partner").reset_index()


def exports_top_as_of(tables: dict[str, pd.DataFrame]) -> str | None:
    """The last month in the destination ranking (the table itself has no month column)."""
    c = _top_product_by_partner(tables)
    return str(c["month"].max()) if len(c) else None


def export_unit_value(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """FOB USD per kg of all-destination (World) exports, by month and product."""
    c = tables["comtrade"]
    w = c[(c["partner"] == "World") & (c["net_kg"] > 0)]
    out = w.groupby(["month", "product"], as_index=False)[["fob_usd", "net_kg"]].sum()
    out["usd_per_kg"] = out["fob_usd"] / out["net_kg"]
    return out[["month", "product", "usd_per_kg"]]


def crop_by_year(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    crop = tables["giresun_crop"]
    usd = target_series(tables["giresun_price"]).dropna()
    avg = usd.groupby(_season_start(usd.index)).mean()
    years = crop["year"].astype(int)
    nat = tables.get("national_crop")
    national = (
        nat.set_index("year")["estimate_t"].astype(float).reindex(years)
        if nat is not None
        else pd.Series(np.nan, index=years)
    )
    return pd.DataFrame(
        {
            "year": years.to_numpy(),
            "season": [_label_of_start(int(y)) for y in years],
            "giresun_estimate_t": crop["estimate_t"].astype(float).to_numpy(),
            "giresun_registered_t": crop["registered_t"].astype(float).to_numpy(),
            "national_estimate_t": national.to_numpy(),
            "season_avg_usd": avg.reindex(years).to_numpy(),
        }
    )


def frost_by_year(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    w = tables["weather"]
    years = sorted(pd.to_datetime(w["date"]).dt.year.unique())
    may = pd.PeriodIndex([pd.Period(year=int(y), month=5, freq="M") for y in years])
    frost = frost_feature(w, may)  # value visible in May of each year
    return pd.DataFrame({"year": [int(y) for y in years], "frost_days": frost.to_numpy()}).dropna()


BUILDERS: dict[str, tuple[Callable[[dict[str, pd.DataFrame]], pd.DataFrame], tuple[str, ...]]] = {
    "prices_monthly": (prices_monthly, ("giresun_price",)),
    "ordu_monthly": (ordu_monthly, ("ordu_daily", "giresun_price")),
    "exports_monthly": (exports_monthly, ("comtrade",)),
    "exports_top": (exports_top, ("comtrade",)),
    "export_unit_value": (export_unit_value, ("comtrade",)),
    "crop_by_year": (crop_by_year, ("giresun_crop", "giresun_price")),
    "frost_by_year": (frost_by_year, ("weather",)),
}
# Outputs whose manifest "as of" is not their latest month/year column: {output: fn(tables)}.
AS_OF = {"exports_top": exports_top_as_of}


# --- Excel workbook content for this crop ---------------------------------------------

PRICE, KG, SHARE, TONNES = "0.00", "#,##0", "0.0%", "#,##0"

# sheet -> (csv name, {column: (header, number format or None)})
WORKBOOK_SHEETS = {
    "Prices": ("prices_monthly.csv", {
        "month": ("Month", None), "season": ("Season", None), "usd_kg": ("USD/kg", PRICE),
        "try_kg": ("TL/kg", PRICE), "usd_try": ("TL per USD", "0.0000")}),
    "Ordu": ("ordu_monthly.csv", {
        "month": ("Month", None), "season": ("Season", None), "try_kg": ("TL/kg", PRICE),
        "usd_kg": ("USD/kg", PRICE), "trade_days": ("Trading days", "0")}),
    "Exports": ("exports_monthly.csv", {
        "month": ("Month", None), "product": ("Product", None), "partner": ("Destination", None),
        "net_kg": ("Net weight (kg)", KG), "fob_usd": ("FOB value (USD)", KG)}),
    "Top destinations": ("exports_top.csv", {
        "partner": ("Destination", None), "net_kg": ("Net weight (kg)", KG),
        "fob_usd": ("FOB value (USD)", KG), "share": ("Share of exports", SHARE)}),
    "Crop": ("crop_by_year.csv", {
        "year": ("Year", "0"), "season": ("Season", None),
        "giresun_estimate_t": ("Giresun estimate (t)", TONNES),
        "giresun_registered_t": ("Giresun registered (t)", TONNES),
        "national_estimate_t": ("National estimate (t)", TONNES),
        "season_avg_usd": ("Season average (USD/kg)", PRICE)}),
    "Forecast range": ("price_range.csv", {
        "horizon": ("Horizon (months)", "0"), "target_month": ("Target month", None),
        "q05": ("5th percentile (USD/kg)", PRICE), "q10": ("10th percentile (USD/kg)", PRICE),
        "q50": ("Median (USD/kg)", PRICE), "q90": ("90th percentile (USD/kg)", PRICE),
        "q95": ("95th percentile (USD/kg)", PRICE), "from_month": ("Forecast from month", None),
        "from_usd": ("Price at forecast origin (USD/kg)", PRICE)}),
}

WORKBOOK_SHEET_NOTES = {
    "Prices": "Monthly Giresun price, USD/kg and TL/kg",
    "Ordu": "Monthly Ordu exchange price",
    "Exports": "Monthly exports by destination",
    "Top destinations": "Largest export destinations",
    "Crop": "Crop size by year and season average price",
    "Forecast range": "Empirical price range by horizon, in USD/kg",
}

WORKBOOK_SOURCES = [
    ("UN Comtrade", "Monthly export volumes and values by destination (HS 080221, 080222)",
     "https://comtradeplus.un.org/", "Credit the source; see provider terms"),
    ("FAOSTAT", "Annual national production statistics",
     "https://www.fao.org/faostat/", "CC BY 4.0"),
    ("TOBB", "Commodity exchange price records (TOBB exchange price query)",
     "https://borsa.tobb.org.tr/", "Credit the source; see provider terms"),
    ("Giresun Commodity Exchange", "Monthly prices, crop estimates and trade volumes",
     "https://www.giresuntb.org.tr/", "Credit the source; see provider terms"),
    ("Ordu Commodity Exchange", "Daily prices, published by the exchange as a public Google Sheet",
     "https://docs.google.com/spreadsheets/d/1aeIzaRkKD4XvKZMRu5A4ZJywzNNUn6Ww/htmlview",
     "Credit the source; see provider terms"),
    ("Open-Meteo", "Historical daily weather (frost days)",
     "https://open-meteo.com/", "CC BY 4.0"),
    ("ECB", "Daily euro foreign-exchange reference rates",
     "https://data.ecb.europa.eu/", "Free reuse with the source acknowledged"),
    ("OECD", "Consumer price index",
     "https://data-explorer.oecd.org/", "CC BY 4.0"),
]



# Data explorer: each exchange's monthly sheet above (its file and column labels).
EXPLORER_SHEETS = {"Giresun": "Prices", "Ordu": "Ordu"}

# Methods page facts that live in the forecasting reports, not in the site data.
HOLDOUT_PERIOD = ("2024-10", "2026-09")  # reports/forecast_results.md: final holdout
TIMING_NOTE = (
    "A harvest's crop estimate is used only from August of that year, when it is normally "
    "out; moving every estimate a month later changed the error ratios by at most 0.03, so "
    "the rule shows no sign of a leak."  # reports/crop_estimate_findings.md, section 3
)

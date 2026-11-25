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
from hazelnut.site.i18n import has as i18n_has
from hazelnut.site.i18n import t
from hazelnut.site.labels import partner_label

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
# Sheet names, column headers, notes and source credits are this crop's entries in
# site/i18n/{en,tr}.yml ("hazelnut.*"), read in the active language when this module loads.

PRICE, KG, SHARE, TONNES = "0.00", "#,##0", "0.0%", "#,##0"


def _sheet(key: str, csv: str, columns: dict[str, str | None]) -> tuple[str, tuple[str, dict]]:
    """(sheet name, (csv name, {column: (header, number format or None)}))."""
    headers = {c: (t(f"hazelnut.column.{c}"), fmt) for c, fmt in columns.items()}
    return t(f"hazelnut.sheet.{key}.name"), (csv, headers)


# Sheet key -> csv and {column: number format}, in workbook order.
_SHEETS = {
    "prices": ("prices_monthly.csv", {"month": None, "season": None, "usd_kg": PRICE,
                                      "try_kg": PRICE, "usd_try": "0.0000"}),
    "ordu": ("ordu_monthly.csv", {"month": None, "season": None, "try_kg": PRICE,
                                  "usd_kg": PRICE, "trade_days": "0"}),
    "exports": ("exports_monthly.csv", {"month": None, "product": None, "partner": None,
                                        "net_kg": KG, "fob_usd": KG}),
    "top": ("exports_top.csv", {"partner": None, "net_kg": KG, "fob_usd": KG, "share": SHARE}),
    "crop": ("crop_by_year.csv", {"year": "0", "season": None, "giresun_estimate_t": TONNES,
                                  "giresun_registered_t": TONNES, "national_estimate_t": TONNES,
                                  "season_avg_usd": PRICE}),
    "range": ("price_range.csv", {"horizon": "0", "target_month": None, "q05": PRICE,
                                  "q10": PRICE, "q50": PRICE, "q90": PRICE, "q95": PRICE,
                                  "from_month": None, "from_usd": PRICE}),
}

# sheet -> (csv name, {column: (header, number format or None)})
WORKBOOK_SHEETS = dict(_sheet(key, csv, cols) for key, (csv, cols) in _SHEETS.items())

# Text values shown in the language's words, by column (every sheet): destinations by
# their country name ("Other" as exports.other), UN Comtrade's product codes by the
# "hazelnut.product.<code>" labels. A value without a label stays as it is.
def _product_label(code: str) -> str:
    key = f"hazelnut.product.{code}"
    return t(key) if i18n_has(key) else code


WORKBOOK_VALUES = {"partner": partner_label, "product": _product_label}

WORKBOOK_SHEET_NOTES = {t(f"hazelnut.sheet.{key}.name"): t(f"hazelnut.sheet.{key}.note")
                        for key in _SHEETS}

# (provider, what we use, URL, credit and terms); the words are "hazelnut.source.<key>.*".
_SOURCE_URLS = {
    "comtrade": "https://comtradeplus.un.org/",
    "faostat": "https://www.fao.org/faostat/",
    "tobb": "https://borsa.tobb.org.tr/",
    "giresun": "https://www.giresuntb.org.tr/",
    "ordu": "https://docs.google.com/spreadsheets/d/1aeIzaRkKD4XvKZMRu5A4ZJywzNNUn6Ww/htmlview",
    "open_meteo": "https://open-meteo.com/",
    "ecb": "https://data.ecb.europa.eu/",
    "oecd": "https://data-explorer.oecd.org/",
}
WORKBOOK_SOURCES = [
    (t(f"hazelnut.source.{key}.name"), t(f"hazelnut.source.{key}.what"), url,
     t(f"hazelnut.source.{key}.terms"))
    for key, url in _SOURCE_URLS.items()
]


# Data explorer: each exchange's monthly sheet above (its file and column labels).
EXPLORER_SHEETS = {"Giresun": t("hazelnut.sheet.prices.name"), "Ordu": t("hazelnut.sheet.ordu.name")}

# Methods page facts that live in the forecasting reports, not in the site data.
HOLDOUT_PERIOD = ("2024-10", "2026-09")  # reports/forecast_results.md: final holdout
TIMING_NOTE = t("hazelnut.timing_note")  # reports/crop_estimate_findings.md, section 3

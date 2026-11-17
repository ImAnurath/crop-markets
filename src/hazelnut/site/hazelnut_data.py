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
    OLD_LIRA_FACTOR,
    frost_feature,
    fx_feature,
    target_series,
    target_series_try,
)


def season_label(month: pd.Period) -> str:
    start = month.year if month.month >= 9 else month.year - 1
    return f"{start}/{(start + 1) % 100:02d}"


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


def exports_top(tables: dict[str, pd.DataFrame], months: int = 12, top: int = 10) -> pd.DataFrame:
    """Shelled exports by partner over the last ``months`` months with data; share is of net_kg."""
    c = tables["comtrade"]
    c = c[(c["product"] == "shelled") & (c["partner"] != "World")]
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
    national = tables["national_crop"].set_index("year")["estimate_t"]
    years = crop["year"].astype(int)
    return pd.DataFrame(
        {
            "year": years.to_numpy(),
            "season": [_label_of_start(int(y)) for y in years],
            "giresun_estimate_t": crop["estimate_t"].astype(float).to_numpy(),
            "giresun_registered_t": crop["registered_t"].astype(float).to_numpy(),
            "national_estimate_t": national.reindex(years).astype(float).to_numpy(),
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
    "crop_by_year": (crop_by_year, ("giresun_crop", "giresun_price", "national_crop")),
    "frost_by_year": (frost_by_year, ("weather",)),
}

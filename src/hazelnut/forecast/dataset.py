"""Modelling dataset: the target price series and an inputs frame aligned by information timing.

Row ``t`` of the inputs frame holds only what was known at the end of month ``t``.
Every timing shift happens here, once, so methods never need to think about it:

- usd_try:          USD/TRY of month t (old-lira rows divided by 1,000,000)
- cpi:              Turkish CPI of month t-1
- exports_kg:       Turkey shelled exports to World (HS 080222) of month t-3
- fao_production_t: FAOSTAT Türkiye production for year Y, visible from December of Y+1
- crop_estimate_t,
  crop_change:      Giresun crop estimate for harvest year Y, visible from August of Y;
                    crop_change = log(est_Y / est_{Y-1})
- frost_days:       March-April days with min temperature < 0, averaged over locations,
                    for year Y, visible from May of Y
- volume_kg:        Giresun registered volume (all buyers) of month t
- nat_crop_estimate_t,
  nat_crop_change:  official national crop estimate for harvest year Y (data/manual), visible from
                    the month in its visible_from column (August of Y unless the announcement is
                    known to be later); nat_crop_change = log(est_Y / est_{Y-1})
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "interim"
MANUAL_DIR = DATA_DIR.parent / "manual"
NATIONAL_CROP_FILE = "national_crop_estimate.csv"
HORIZONS = (1, 3, 6)
FIRST_ORIGIN = pd.Period("2005-01", "M")
HOLDOUT_MONTHS = 24
SHOCK_PERIODS: list[tuple[str, str]] = [
    ("2005-01", "2005-12"),
    ("2014-01", "2015-12"),
    ("2025-01", "2025-12"),
]
TARGET_START = pd.Period("1995-01", "M")

_FILES = {
    "giresun_price": "giresun_monthly_price.csv",
    "giresun_crop": "giresun_crop.csv",
    "giresun_volume": "giresun_monthly_volume.csv",
    "weather": "weather_daily.csv",
    "comtrade": "comtrade_monthly.csv",
    "faostat": "faostat_production.csv",
    "cpi": "cpi_monthly.csv",
}


def load_tables(data_dir: Path = DATA_DIR, manual_dir: Path = MANUAL_DIR) -> dict[str, pd.DataFrame]:
    tables = {key: pd.read_csv(data_dir / name) for key, name in _FILES.items()}
    if (manual_dir / NATIONAL_CROP_FILE).exists():
        tables["national_crop"] = pd.read_csv(manual_dir / NATIONAL_CROP_FILE)
    return tables


def _year_month_index(df: pd.DataFrame) -> pd.PeriodIndex:
    return pd.PeriodIndex(
        [pd.Period(year=int(y), month=int(m), freq="M") for y, m in zip(df["year"], df["month"])]
    )


def _lagged(values: pd.Series, months: pd.PeriodIndex, lag: int) -> pd.Series:
    """Row m gets the value of month m - lag (NaN where that month is absent)."""
    shifted = values.copy()
    shifted.index = shifted.index + lag
    return shifted.reindex(months)


def _annual(values: pd.Series, visible_year: np.ndarray, months: pd.PeriodIndex) -> pd.Series:
    """Row m gets ``values[visible_year[m]]`` (NaN where that year is absent)."""
    return pd.Series(values.reindex(visible_year).to_numpy(), index=months)


def target_series(giresun_price: pd.DataFrame) -> pd.Series:
    s = pd.Series(
        giresun_price["price_avg_usd"].to_numpy(dtype=float), index=_year_month_index(giresun_price)
    )
    s = s[s.index >= TARGET_START]
    last = s.last_valid_index()
    idx = pd.period_range(TARGET_START, last, freq="M")
    return s.reindex(idx).rename("price_usd")


def crop_feature(crop: pd.DataFrame, months: pd.PeriodIndex) -> pd.DataFrame:
    est = crop.set_index("year")["estimate_t"].astype(float).sort_index()
    change = np.log(est / est.reindex(est.index - 1).to_numpy())
    year = np.asarray(months.year)
    visible = np.where(np.asarray(months.month) >= 8, year, year - 1)
    return pd.DataFrame(
        {
            "crop_estimate_t": _annual(est, visible, months),
            "crop_change": _annual(change, visible, months),
        },
        index=months,
    )


def national_crop_feature(national: pd.DataFrame, months: pd.PeriodIndex) -> pd.DataFrame:
    """Row m holds the estimate of the latest harvest year whose ``visible_from`` month is <= m."""
    t = national.sort_values("year")
    est = pd.Series(t["estimate_t"].astype(float).to_numpy(), index=t["year"].astype(int))
    change = np.log(est / est.reindex(est.index - 1).to_numpy())
    visible = pd.PeriodIndex(t["visible_from"], freq="M")
    if not visible.is_monotonic_increasing:
        raise ValueError("visible_from must not go backwards from one year to the next")
    pos = np.searchsorted(visible.asi8, months.asi8, side="right") - 1
    year = np.where(pos >= 0, est.index.to_numpy()[np.clip(pos, 0, None)], -1)
    return pd.DataFrame(
        {
            "nat_crop_estimate_t": _annual(est, year, months),
            "nat_crop_change": _annual(change, year, months),
        },
        index=months,
    )


def frost_feature(weather: pd.DataFrame, months: pd.PeriodIndex) -> pd.Series:
    dates = pd.to_datetime(weather["date"])
    spring = weather[dates.dt.month.isin([3, 4])].assign(year=dates.dt.year)
    per_location = (
        spring.assign(frost=spring["temperature_2m_min"] < 0)
        .groupby(["year", "location"])["frost"]
        .sum()
    )
    per_year = per_location.groupby(level="year").mean().astype(float)
    year = np.asarray(months.year)
    visible = np.where(np.asarray(months.month) >= 5, year, year - 1)
    return _annual(per_year, visible, months).rename("frost_days")


def fao_feature(fao: pd.DataFrame, months: pd.PeriodIndex) -> pd.Series:
    rows = fao[(fao["area"] == "Türkiye") & (fao["element"] == "Production")]
    prod = rows.set_index("year")["value"].astype(float)
    year = np.asarray(months.year)
    visible = np.where(np.asarray(months.month) == 12, year - 1, year - 2)
    return _annual(prod, visible, months).rename("fao_production_t")


def exports_feature(comtrade: pd.DataFrame, months: pd.PeriodIndex) -> pd.Series:
    rows = comtrade[(comtrade["partner"] == "World") & (comtrade["product"] == "shelled")]
    kg = rows.groupby(pd.PeriodIndex(rows["month"], freq="M"))["net_kg"].sum().astype(float)
    return _lagged(kg, months, 3).rename("exports_kg")


def fx_feature(giresun_price: pd.DataFrame, months: pd.PeriodIndex) -> pd.Series:
    rate = giresun_price["usd_try"].astype(float).to_numpy()
    old = giresun_price["old_lira"].astype(bool).to_numpy()
    s = pd.Series(np.where(old, rate / 1_000_000, rate), index=_year_month_index(giresun_price))
    return s.reindex(months).rename("usd_try")


def cpi_feature(cpi: pd.DataFrame, months: pd.PeriodIndex) -> pd.Series:
    s = pd.Series(cpi["cpi"].astype(float).to_numpy(), index=pd.PeriodIndex(cpi["month"], freq="M"))
    return _lagged(s, months, 1).rename("cpi")


def volume_feature(volume: pd.DataFrame, months: pd.PeriodIndex) -> pd.Series:
    kg = volume.groupby(_year_month_index(volume))["quantity_kg"].sum().astype(float)
    return kg.reindex(months).rename("volume_kg")


def build_inputs(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    months = target_series(tables["giresun_price"]).index
    parts = [
        fx_feature(tables["giresun_price"], months),
        cpi_feature(tables["cpi"], months),
        exports_feature(tables["comtrade"], months),
        fao_feature(tables["faostat"], months),
        crop_feature(tables["giresun_crop"], months),
        frost_feature(tables["weather"], months),
        volume_feature(tables["giresun_volume"], months),
    ]
    if "national_crop" in tables:
        parts.append(national_crop_feature(tables["national_crop"], months))
    return pd.concat(parts, axis=1)


def load_dataset(data_dir: Path = DATA_DIR) -> tuple[pd.Series, pd.DataFrame]:
    tables = load_tables(data_dir)
    return target_series(tables["giresun_price"]), build_inputs(tables)

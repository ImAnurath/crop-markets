"""Readable names shared by the site pages and the Excel workbook."""
from __future__ import annotations

METHOD_NAMES = {
    "naive": "Naive", "seasonal_naive": "Seasonal naive", "sarima": "SARIMA",
    "sarimax": "SARIMAX", "season_reg": "Season regression", "lightgbm": "LightGBM",
    "chronos": "Chronos-Bolt",
    # Range (quantile) forecasts
    "naive_emp": "Naive range (past moves)", "naive_vol": "Naive range, volatility-scaled",
    "lightgbm_q": "LightGBM quantiles",
}


# The exports table's bucket for every partner outside the top ten.
OTHER_PARTNER = "Other"


# Stat-tile labels for a crop estimate, whole sentences with named fields.
CROP_ESTIMATE_LABEL = "{source} crop estimate, {year}"
CROP_ESTIMATE_LABEL_NO_YEAR = "{source} crop estimate"


def method_name(method: str) -> str:
    """Readable forecasting-method name; unknown methods keep their code name."""
    return METHOD_NAMES.get(method, method)

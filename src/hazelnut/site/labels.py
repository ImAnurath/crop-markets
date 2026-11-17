"""Readable names shared by the site pages and the Excel workbook."""
from __future__ import annotations

METHOD_NAMES = {
    "naive": "Naive", "seasonal_naive": "Seasonal naive", "sarima": "SARIMA",
    "sarimax": "SARIMAX", "season_reg": "Season regression", "lightgbm": "LightGBM",
    "chronos": "Chronos-Bolt",
}


def method_name(method: str) -> str:
    """Readable forecasting-method name; unknown methods keep their code name."""
    return METHOD_NAMES.get(method, method)

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


# The Methods page card that explains each method (its anchor id).
METHOD_ANCHORS = {
    "naive": "naive", "seasonal_naive": "seasonal-naive", "sarima": "sarima",
    "sarimax": "sarimax", "season_reg": "season-regression", "lightgbm": "lightgbm",
    "chronos": "chronos-bolt",
}


# Shown above a table that is wider than its card, so a reader knows it scrolls sideways.
SCROLL_HINT = "Scroll for more →"


# The exports table's bucket for every partner outside the top ten.
OTHER_PARTNER = "Other"


# Stat-tile labels for a crop estimate, whole sentences with named fields.
CROP_ESTIMATE_LABEL = "{source} crop estimate, {year}"
CROP_ESTIMATE_LABEL_NO_YEAR = "{source} crop estimate"


HOLDOUT_LUCK_NOTE = ("Each score that beat naive in the holdout had lost to naive at that same "
                     "horizon in development, so these wins look like luck, not skill.")
HOLDOUT_NO_REPEAT_NOTE = ("None of the holdout scores that beat naive also beat it in "
                          "development at the same horizon.")

# Frost page subtitle when there are too few years to correlate.
FROST_CROP_FALLBACK = "Spring frost days against the {source} crop estimate."
FROST_CROP_FALLBACK_NO_SOURCE = "Spring frost days against the crop estimate."


def method_name(method: str) -> str:
    """Readable forecasting-method name; unknown methods keep their code name."""
    return METHOD_NAMES.get(method, method)

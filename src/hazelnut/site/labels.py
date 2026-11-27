"""Readable names shared by the site pages and the Excel workbook.

The words themselves live in ``site/i18n/{en,tr}.yml`` (see ``hazelnut.site.i18n``).
"""
from __future__ import annotations

from hazelnut.site.i18n import country_name, has, t

# The forecasting methods with a readable name (site/i18n "method.<code>").
METHODS = ("naive", "seasonal_naive", "sarima", "sarimax", "season_reg", "lightgbm", "chronos",
           # Range (quantile) forecasts
           "naive_emp", "naive_vol", "lightgbm_q")


# The Methods page card that explains each method (its anchor id).
METHOD_ANCHORS = {
    "naive": "naive", "seasonal_naive": "seasonal-naive", "sarima": "sarima",
    "sarimax": "sarimax", "season_reg": "season-regression", "lightgbm": "lightgbm",
    "chronos": "chronos-bolt",
}


# The exports table's bucket for every partner outside the top ten. This is the value in
# the data (exports_top.csv); pages show it as ``other_partner_label()``.
OTHER_PARTNER = "Other"


def other_partner_label() -> str:
    return t("exports.other")


def partner_label(partner: str) -> str:
    """An export destination as the pages show it: the "Other" bucket as
    ``other_partner_label()``, a country by ``i18n.country_name``."""
    return other_partner_label() if partner == OTHER_PARTNER else country_name(partner)


def scroll_hint() -> str:
    """Shown above a table that is wider than its card, so a reader knows it scrolls."""
    return t("table.scroll_hint")


def crop_estimate_label(source: str, year: int | None = None) -> str:
    """Stat-tile and axis label for a crop estimate: "Giresun crop estimate, 2026"."""
    if year is None:
        return t("crop_estimate.label_no_year", source=source)
    return t("crop_estimate.label", source=source, year=year)


def crop_figures_note(source: str) -> str:
    """Footnote under the crop-and-frost chart naming whose crop figures are plotted."""
    return t("crop_estimate.figures_note", source=source)


def method_name(method: str) -> str:
    """Readable forecasting-method name; unknown methods keep their code name."""
    key = f"method.{method}"
    return t(key) if has(key) else method

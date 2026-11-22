"""Synthetic interim tables (2004-09 .. 2007-12) in the exact column layouts of data/interim."""

import numpy as np
import pandas as pd
import pytest

OLD_LIRA = 1_000_000
MONTHS = pd.period_range("2004-09", "2007-12", freq="M")  # 40 months
PLANTED_FROST = {2005: 2.5, 2006: 1.0, 2007: 0.0}  # mean March-April sub-zero days per location


def usd_price(i: int) -> float:
    """Stable real price with a mild seasonal wiggle (so old/new lira rows are comparable)."""
    return 3.0 + 0.1 * (i % 12)


def _giresun_price() -> pd.DataFrame:
    rows = []
    for i, m in enumerate(MONTHS):
        old = m < pd.Period("2005-01", "M")
        rate = 1.4 * (OLD_LIRA if old else 1.0)
        usd = usd_price(i)
        rows.append(
            dict(
                year=m.year, month=m.month, usd_try=rate,
                price_min_try=usd * rate * 0.95, price_max_try=usd * rate * 1.05,
                price_avg_try=usd * rate,
                price_min_usd=usd * 0.95, price_max_usd=usd * 1.05, price_avg_usd=usd,
                old_lira=old,
            )
        )
    return pd.DataFrame(rows)


def _comtrade() -> pd.DataFrame:
    rows = []
    small = ["Spain", "Poland", "Jordan", "Iraq", "Chile"]
    for i, m in enumerate(MONTHS):
        shares = {"Germany": 500_000, "Italy": 300_000}
        shares.update({p: 10_000 * (k + 1) for k, p in enumerate(small)})
        for partner, kg in {**shares, "World": sum(shares.values())}.items():
            rows.append((str(m), "080222", "shelled", partner, float(kg), kg * (6.0 + 0.05 * (i % 6))))
        rows.append((str(m), "080221", "in_shell", "Germany", 20_000.0, 60_000.0))
        rows.append((str(m), "080221", "in_shell", "World", 20_000.0, 60_000.0))
    return pd.DataFrame(rows, columns=["month", "hs_code", "product", "partner", "net_kg", "fob_usd"])


def _weather() -> pd.DataFrame:
    days = pd.date_range("2005-03-01", "2007-04-30", freq="D")
    rows = []
    frost = {  # (location, date) planted sub-zero days
        **{("duzce", f"2005-03-{d:02d}"): -2.0 for d in (3, 4, 5)},
        ("giresun", "2005-03-10"): -1.0,
        ("giresun", "2005-04-02"): -0.5,
        ("duzce", "2006-04-01"): -3.0,
        ("duzce", "2006-04-02"): -3.0,
    }
    for loc in ("duzce", "giresun"):
        for d in days:
            tmin = frost.get((loc, d.strftime("%Y-%m-%d")), 5.0)
            rows.append((d.strftime("%Y-%m-%d"), tmin + 8, tmin, tmin + 4, 0.0, 0.0, loc))
    return pd.DataFrame(
        rows,
        columns=["date", "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
                 "precipitation_sum", "snowfall_sum", "location"],
    )


def _ordu_daily() -> pd.DataFrame:
    rows = []
    for i, m in enumerate(MONTHS):
        old = m < pd.Period("2005-01", "M")
        for d in (3, 10, 17):
            price = usd_price(i) * 1.4 * (OLD_LIRA if old else 1.0)
            rows.append((f"{m}-{d:02d}", price, False, old))
    return pd.DataFrame(rows, columns=["date", "price", "special_terms", "old_lira"])


@pytest.fixture(autouse=True)
def english_by_default(monkeypatch):
    """Site code runs in English unless a test sets the language (see hazelnut.site.i18n)."""
    monkeypatch.delenv("QUARTO_PROFILE", raising=False)
    monkeypatch.delenv("SITE_LANG", raising=False)


@pytest.fixture
def tiny_tables() -> dict[str, pd.DataFrame]:
    return {
        "giresun_price": _giresun_price(),
        "giresun_crop": pd.DataFrame(
            {"year": [2004, 2005, 2006], "estimate_t": [500000, 450000, 520000],
             "registered_t": [400000, 380000, 410000], "ratio_pct": [80.0, 84.4, 78.8],
             "partial": [False, False, False]}
        ),
        "giresun_volume": pd.DataFrame(
            {"season": [2004, 2004], "year": [2004, 2004], "month": [9, 9],
             "buyer": ["trader", "cooperative"], "quantity_kg": [1000, 200],
             "value_try": [4.2e9, 8.0e8], "price_try": [4.2e6, 4.0e6]}
        ),
        "weather": _weather(),
        "comtrade": _comtrade(),
        "faostat": pd.DataFrame(
            {"area": ["Türkiye"] * 2, "element": ["Production"] * 2, "year": [2004, 2005],
             "unit": ["t"] * 2, "value": [600000.0, 650000.0], "flag": ["A", "A"]}
        ),
        "cpi": pd.DataFrame(
            {"month": [str(m) for m in MONTHS], "cpi": np.linspace(1.0, 1.5, len(MONTHS))}
        ),
        "national_crop": pd.DataFrame(
            {"year": [2004, 2005, 2006], "estimate_t": [480000, 440000, 510000],
             "visible_from": ["2004-08", "2005-08", "2006-08"],
             "source_url": ["x"] * 3, "note": [""] * 3}
        ),
        "ordu_daily": _ordu_daily(),
    }

import numpy as np
import pandas as pd
import pytest

from hazelnut.forecast.dataset import (
    DATA_DIR,
    cpi_feature,
    crop_feature,
    exports_feature,
    fao_feature,
    frost_feature,
    fx_feature,
    load_dataset,
    target_series,
    volume_feature,
)


def M(s: str) -> pd.Period:
    return pd.Period(s, "M")


def months(start: str, end: str) -> pd.PeriodIndex:
    return pd.period_range(start, end, freq="M")


def test_crop_estimate_visible_from_august():
    crop = pd.DataFrame({"year": [2022, 2023], "estimate_t": [100.0, 50.0]})
    f = crop_feature(crop, months("2023-06", "2023-09"))
    assert f.loc[M("2023-07"), "crop_estimate_t"] == 100.0
    assert f.loc[M("2023-08"), "crop_estimate_t"] == 50.0
    assert f.loc[M("2023-08"), "crop_change"] == pytest.approx(np.log(0.5))


def test_frost_visible_from_may():
    # 2013: no frost anywhere. 2014: 2 frost days in March-April at "a", 0 at "b" -> mean 1.0.
    # A frost day in February 2014 must not count.
    rows = [
        ("2013-03-10", 2.0, "a"), ("2013-04-10", 1.0, "b"),
        ("2014-02-10", -5.0, "a"),
        ("2014-03-10", -1.0, "a"), ("2014-04-02", -0.5, "a"), ("2014-04-03", 3.0, "a"),
        ("2014-03-10", 4.0, "b"), ("2014-04-10", 0.0, "b"),
    ]
    weather = pd.DataFrame(rows, columns=["date", "temperature_2m_min", "location"])
    f = frost_feature(weather, months("2014-04", "2014-05"))
    assert f.name == "frost_days"
    assert f.loc[M("2014-04")] == 0.0
    assert f.loc[M("2014-05")] == 1.0


def test_fao_year_visible_from_december_next_year():
    fao = pd.DataFrame({
        "area": ["Türkiye", "Türkiye", "Türkiye", "Italy"],
        "element": ["Production", "Production", "Area harvested", "Production"],
        "year": [2019, 2020, 2020, 2020],
        "unit": ["t", "t", "ha", "t"],
        "value": [10.0, 20.0, 999.0, 555.0],
    })
    f = fao_feature(fao, months("2021-11", "2021-12"))
    assert f.name == "fao_production_t"
    assert f.loc[M("2021-11")] == 10.0
    assert f.loc[M("2021-12")] == 20.0


def test_exports_lag_three_months():
    comtrade = pd.DataFrame({
        "month": ["2020-03", "2020-03", "2020-03", "2020-04"],
        "hs_code": [80222, 80222, 80221, 80222],
        "product": ["shelled", "shelled", "in_shell", "shelled"],
        "partner": ["World", "Germany", "World", "World"],
        "net_kg": [7.0, 100.0, 50.0, 9.0],
    })
    f = exports_feature(comtrade, months("2020-05", "2020-07"))
    assert f.name == "exports_kg"
    assert np.isnan(f.loc[M("2020-05")])
    assert f.loc[M("2020-06")] == 7.0
    assert f.loc[M("2020-07")] == 9.0


def test_cpi_lag_one_month():
    cpi = pd.DataFrame({"month": ["2020-05", "2020-06"], "cpi": [3.0, 4.0]})
    f = cpi_feature(cpi, months("2020-06", "2020-06"))
    assert f.name == "cpi"
    assert f.loc[M("2020-06")] == 3.0


def test_fx_old_lira_converted():
    price = pd.DataFrame({
        "year": [1995, 2010], "month": [1, 1],
        "usd_try": [40000.0, 1.5], "old_lira": [True, False],
    })
    f = fx_feature(price, pd.PeriodIndex([M("1995-01"), M("2010-01")]))
    assert f.name == "usd_try"
    assert f.loc[M("1995-01")] == pytest.approx(0.04)
    assert f.loc[M("2010-01")] == 1.5


def test_volume_sums_buyers_and_duplicate_august():
    volume = pd.DataFrame({
        "season": [2019, 2019, 2020, 2020],
        "year": [2020, 2020, 2020, 2020],
        "month": [8, 8, 8, 9],
        "buyer": ["trader", "tmo", "trader", "trader"],
        "quantity_kg": [10, 20, 5, 1],
    })
    f = volume_feature(volume, months("2020-08", "2020-08"))
    assert f.name == "volume_kg"
    assert f.loc[M("2020-08")] == 35


def test_target_keeps_missing_months_as_nan():
    price = pd.DataFrame({
        "year": [1994, 1995, 1995, 1995], "month": [12, 1, 2, 4],
        "price_avg_usd": [9.0, 1.0, 2.0, 4.0],
    })
    t = target_series(price)
    assert t.name == "price_usd"
    assert list(t.index) == list(months("1995-01", "1995-04"))
    assert np.isnan(t.loc[M("1995-03")])
    assert t.loc[M("1995-04")] == 4.0


@pytest.mark.skipif(not (DATA_DIR / "giresun_monthly_price.csv").exists(), reason="data/interim not built")
def test_real_data_shapes():
    target, inputs = load_dataset()
    assert target.index[0] == M("1995-01")
    assert not target.isna().any()
    assert inputs.index.equals(target.index)
    assert np.isfinite(inputs.loc[M("2015-08"), "crop_change"])

import pandas as pd

from hazelnut.forecast import dataset
from hazelnut.site import hazelnut_data as hd
from tests.site.conftest import MONTHS, PLANTED_FROST, usd_price


def test_prices_monthly_rescales_old_lira(tiny_tables):
    df = hd.prices_monthly(tiny_tables)
    p = df.set_index("month")
    ratio = p.loc["2004-12", "try_kg"] / p.loc["2005-01", "try_kg"]
    assert 0.5 < ratio < 2
    assert list(df.columns) == ["month", "season", "usd_kg", "try_kg", "usd_try"]
    assert p.loc["2004-12", "season"] == "2004/05"


def test_season_label_september_starts_season():
    assert hd.season_label(pd.Period("2025-09")) == "2025/26"
    assert hd.season_label(pd.Period("2026-08")) == "2025/26"


def test_exports_top_shares_sum_to_one_and_has_other(tiny_tables):
    top = hd.exports_top(tiny_tables, months=12, top=3)
    assert abs(top["share"].sum() - 1) < 1e-9
    assert "Other" in set(top["partner"])
    assert len(top) == 4
    assert "World" not in set(top["partner"])


def test_exports_top_without_enough_partners_has_no_other(tiny_tables):
    assert "Other" not in set(hd.exports_top(tiny_tables, top=10)["partner"])


def test_crop_by_year_season_avg_uses_sept_to_aug(tiny_tables):
    c = hd.crop_by_year(tiny_tables).set_index("year")
    idx = {m: i for i, m in enumerate(MONTHS)}
    sept_aug = [usd_price(idx[m]) for m in pd.period_range("2005-09", "2006-08", freq="M")]
    assert abs(c.loc[2005, "season_avg_usd"] - sum(sept_aug) / 12) < 1e-9
    assert c.loc[2005, "season"] == "2005/06"
    assert c.loc[2005, "national_estimate_t"] == 440000


def test_frost_by_year_counts_march_april_subzero(tiny_tables):
    f = hd.frost_by_year(tiny_tables).set_index("year")["frost_days"]
    assert f.to_dict() == PLANTED_FROST


def test_ordu_monthly_rescales_and_counts(tiny_tables):
    o = hd.ordu_monthly(tiny_tables).set_index("month")
    assert (o["trade_days"] == 3).all()
    assert abs(o.loc["2004-12", "try_kg"] - o.loc["2005-01", "try_kg"]) < 1.5
    assert abs(o.loc["2005-01", "usd_kg"] - usd_price(4)) < 1e-9


def test_exports_monthly_and_unit_value(tiny_tables):
    e = hd.exports_monthly(tiny_tables)
    assert list(e.columns) == ["month", "product", "partner", "net_kg", "fob_usd"]
    u = hd.export_unit_value(tiny_tables)
    assert list(u.columns) == ["month", "product", "usd_per_kg"]
    assert set(u["product"]) == {"shelled", "in_shell"}


def test_builders_do_not_mutate_inputs(tiny_tables):
    before = {k: v.copy() for k, v in tiny_tables.items()}
    for fn, _ in hd.BUILDERS.values():
        fn(tiny_tables)
    for k, v in before.items():
        pd.testing.assert_frame_equal(v, tiny_tables[k])


def test_builders_declare_required_tables(tiny_tables):
    # load_tables yields the _FILES keys plus national_crop; ordu_daily is loaded separately
    # by the data-writing task (it is not in dataset._FILES).
    known = set(dataset._FILES) | {"national_crop", "ordu_daily"}
    assert set(hd.BUILDERS) == {
        "prices_monthly", "ordu_monthly", "exports_monthly", "exports_top",
        "export_unit_value", "crop_by_year", "frost_by_year",
    }
    for name, (fn, keys) in hd.BUILDERS.items():
        assert set(keys) <= known, name
        fn({k: tiny_tables[k] for k in keys})  # needs nothing beyond its declared tables

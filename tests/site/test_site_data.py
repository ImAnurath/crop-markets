import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from hazelnut.site.config import CropConfig, LocalCurrency
from hazelnut.site.hazelnut_data import BUILDERS, crop_by_year, prices_monthly
from hazelnut.site.site_data import (
    CORE_OUTPUTS,
    SiteDataError,
    load_interim_tables,
    price_range,
    stat_strip,
    write_site_data,
)

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
CROP = CropConfig(
    "hazelnut", "Hazelnut", "Turkey", (), (), (), ("usd",), LocalCurrency("TL", "try_kg")
)


def test_failed_source_keeps_last_good_and_marks_stale(tiny_tables, tmp_path):
    fresh = write_site_data(CROP, tiny_tables, tmp_path, NOW)
    fresh_as_of = fresh["outputs"]["exports_top"]["as_of"]
    assert fresh_as_of == "2007-12"
    assert fresh["outputs"]["price_range"]["as_of"] == "2007-12"
    before = (tmp_path / "exports_top.csv").read_bytes()
    partial = {k: v for k, v in tiny_tables.items() if k != "comtrade"}
    manifest = write_site_data(CROP, partial, tmp_path, NOW)
    assert (tmp_path / "exports_top.csv").read_bytes() == before
    assert manifest["outputs"]["exports_top"]["stale"] is True
    assert manifest["outputs"]["exports_top"]["as_of"] == fresh_as_of
    assert manifest["outputs"]["prices_monthly"]["stale"] is False
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
    assert manifest["built_at"].startswith("2026-11-17T12:00:00")
    assert manifest["as_of"] == "2007-12"
    assert set(BUILDERS) | {"price_range", "stats"} == set(manifest["outputs"])


def test_no_previous_file_records_empty_stale_entry(tiny_tables, tmp_path):
    partial = {k: v for k, v in tiny_tables.items() if k != "comtrade"}
    manifest = write_site_data(CROP, partial, tmp_path, NOW)
    assert manifest["outputs"]["exports_top"] == {"as_of": None, "rows": 0, "stale": True}
    assert not (tmp_path / "exports_top.csv").exists()


def test_core_failure_raises_and_writes_nothing(tiny_tables, tmp_path):
    write_site_data(CROP, tiny_tables, tmp_path, NOW)
    snap = {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    bad = {k: v for k, v in tiny_tables.items() if k != "giresun_price"}
    with pytest.raises(SiteDataError):
        write_site_data(CROP, bad, tmp_path, NOW)
    assert {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == snap


def test_core_failure_on_fresh_dir_creates_nothing(tmp_path):
    out = tmp_path / "x"
    with pytest.raises(SiteDataError):
        write_site_data(CROP, {}, out, NOW)
    assert not out.exists()
    assert CORE_OUTPUTS == ("prices_monthly", "price_range", "stats")


def test_stats_skip_incomplete_latest_month(tiny_tables):
    prices = prices_monthly(tiny_tables)
    prices.loc[prices.index[-1], "usd_kg"] = float("nan")  # TRY still present
    stats = stat_strip(prices, crop_by_year(tiny_tables))
    assert stats["as_of"] == "2007-11"
    assert all(v == v for v in stats.values() if isinstance(v, float))
    json.dumps(stats, allow_nan=False)


def test_stats_without_crop_have_null_crop_keys(tiny_tables):
    stats = stat_strip(prices_monthly(tiny_tables), None)
    assert stats["crop_estimate_t"] is None and stats["crop_yoy"] is None
    assert stats["crop_year"] is None and stats["usd_kg"] > 0


def test_stats_crop_values(tiny_tables):
    stats = stat_strip(prices_monthly(tiny_tables), crop_by_year(tiny_tables))
    assert stats["crop_year"] == 2006 and stats["crop_estimate_t"] == 520000
    assert stats["crop_yoy"] == pytest.approx(520000 / 450000 - 1)


def test_price_range_is_ordered_and_positive(tiny_tables):
    pr = price_range(prices_monthly(tiny_tables))
    assert list(pr["horizon"]) == [1, 3, 6]
    cols = ["q05", "q10", "q50", "q90", "q95"]
    assert (pr[cols] > 0).all().all()
    assert (pr[cols].diff(axis=1).iloc[:, 1:] >= 0).all().all()
    for _, r in pr.iterrows():
        assert pd.Period(r["target_month"]) == pd.Period(r["from_month"]) + int(r["horizon"])


def test_price_range_uses_last_month_with_both_prices(tiny_tables):
    prices = prices_monthly(tiny_tables)
    prices.loc[prices.index[-1], "usd_kg"] = float("nan")
    assert price_range(prices)["from_month"].iloc[0] == "2007-11"


def test_load_interim_tables_skips_missing(tmp_path):
    assert load_interim_tables(tmp_path, tmp_path) == {}


def test_load_interim_tables_reads_and_skips_unreadable(tmp_path):
    (tmp_path / "ordu_daily.csv").write_text("date,price\n2020-01-01,5\n")
    (tmp_path / "cpi_monthly.csv").write_bytes(b"")  # empty -> unreadable
    t = load_interim_tables(tmp_path, tmp_path)
    assert set(t) == {"ordu_daily"}


def _drop_months(tables, key, months):
    t = dict(tables)
    df = t[key]
    if "year" not in df.columns:
        t[key] = df[~df["month"].isin(months)]
    else:
        stamp = df["year"].astype(str) + "-" + df["month"].map("{:02d}".format)
        t[key] = df[~stamp.isin(months)]
    return t


def test_noncore_row_drop_keeps_last_good_and_marks_stale(tiny_tables, tmp_path):
    first = write_site_data(CROP, tiny_tables, tmp_path, NOW)
    before = (tmp_path / "exports_monthly.csv").read_bytes()
    gone = [f"2006-{m:02d}" for m in range(1, 7)]  # 6 of 40 months: a 15% drop
    notes: list[str] = []
    manifest = write_site_data(CROP, _drop_months(tiny_tables, "comtrade", gone), tmp_path, NOW, notes=notes)
    assert (tmp_path / "exports_monthly.csv").read_bytes() == before
    entry = manifest["outputs"]["exports_monthly"]
    assert entry == {**first["outputs"]["exports_monthly"], "stale": True}
    assert manifest["outputs"]["prices_monthly"]["stale"] is False
    assert any(n.startswith("exports_monthly:") and "row count" in n for n in notes)


def test_small_row_drop_is_still_fresh(tiny_tables, tmp_path):
    write_site_data(CROP, tiny_tables, tmp_path, NOW)
    manifest = write_site_data(CROP, _drop_months(tiny_tables, "comtrade", ["2006-01"]), tmp_path, NOW)
    assert manifest["outputs"]["exports_monthly"]["stale"] is False


def test_core_row_drop_fails_and_writes_nothing(tiny_tables, tmp_path):
    write_site_data(CROP, tiny_tables, tmp_path, NOW)
    snap = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    gone = [f"2007-{m:02d}" for m in range(1, 13)]  # the last 12 of 40 months
    with pytest.raises(SiteDataError, match="row count"):
        write_site_data(CROP, _drop_months(tiny_tables, "giresun_price", gone), tmp_path, NOW)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == snap


def test_notes_name_missing_sources(tiny_tables, tmp_path):
    notes: list[str] = []
    write_site_data(CROP, {k: v for k, v in tiny_tables.items() if k != "weather"}, tmp_path, NOW,
                    notes=notes)
    assert notes == ["frost_by_year: KeyError: \"missing tables: ['weather']\""]

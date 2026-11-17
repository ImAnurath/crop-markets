import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from hazelnut.site.config import CropConfig
from hazelnut.site.site_data import write_site_data
from hazelnut.site.validate import validate_site_data

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
CROP = CropConfig("hazelnut", "Hazelnut", "Turkey", (), (), (), ("usd",))
TODAY = date(2008, 2, 15)  # as_of in the fixture is 2007-12


@pytest.fixture
def out(tiny_tables, tmp_path):
    write_site_data(CROP, tiny_tables, tmp_path, NOW)
    return tmp_path


def _edit_csv(path, fn):
    df = pd.read_csv(path)
    out = fn(df)
    (df if out is None else out).to_csv(path, index=False)


def _problems(out, **kw):
    return validate_site_data(out, kw.pop("today", TODAY), **kw)


def test_good_output_passes(out):
    assert _problems(out) == []


def test_exactly_max_lag_passes_and_five_months_fails(out):
    assert _problems(out, today=date(2008, 3, 31)) == []
    assert any("old" in p or "stale" in p for p in _problems(out, today=date(2008, 5, 1)))


def test_gap_in_months_is_reported(out):
    _edit_csv(out / "prices_monthly.csv", lambda d: d.drop(d.index[d.month == "2006-06"]))
    assert any("2006-06" in p for p in _problems(out))


def test_nonpositive_price_is_reported(out):
    def zero(d):
        d.loc[d.month == "2006-03", "usd_kg"] = 0.0
    _edit_csv(out / "prices_monthly.csv", zero)
    assert any("usd_kg" in p for p in _problems(out))


def test_nan_price_is_reported(out):
    def nan(d):
        d.loc[d.month == "2006-03", "try_kg"] = float("nan")
    _edit_csv(out / "prices_monthly.csv", nan)
    assert any("try_kg" in p for p in _problems(out))


def test_old_as_of_is_reported(out):
    assert any("as_of" in p for p in _problems(out, today=date(2008, 5, 15)))


def test_unordered_range_is_reported(out):
    def swap(d):
        d.loc[0, ["q05", "q95"]] = d.loc[0, ["q95", "q05"]].values
    _edit_csv(out / "price_range.csv", swap)
    assert any("price_range" in p for p in _problems(out))


def test_nonfinite_stat_is_reported_but_null_crop_allowed(out):
    p = out / "stats.json"
    s = json.loads(p.read_text())
    s["crop_estimate_t"] = None
    p.write_text(json.dumps(s))
    assert _problems(out) == []
    s["usd_kg"] = float("inf")
    p.write_text(json.dumps(s))
    assert any("usd_kg" in x for x in _problems(out))


def test_missing_files_are_reported_not_raised(out):
    (out / "stats.json").unlink()
    (out / "manifest.json").unlink()
    probs = _problems(out)
    assert any("stats.json" in x for x in probs) and any("manifest.json" in x for x in probs)


def test_corrupt_json_is_reported_not_raised(out):
    (out / "manifest.json").write_text("{nope")
    assert _problems(out)


def test_manifest_with_null_outputs_is_reported_not_raised(out):
    (out / "manifest.json").write_text(json.dumps({"as_of": "2007-12", "outputs": None}))
    assert any("outputs" in x for x in _problems(out))


def test_four_months_lag_fails(out):
    assert any("as_of" in x for x in _problems(out, today=date(2008, 4, 1)))

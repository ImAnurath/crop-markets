import pytest

from hazelnut.site.config import LocalCurrency, load_crops

_LOCAL = "  local_currency: {label: TL, column: try_kg}\n"


def test_load_crops_reads_hazelnut():
    crop = load_crops()["hazelnut"]
    assert crop.country == "Turkey"
    assert crop.range_currencies == ("usd",)
    assert crop.local_currency == LocalCurrency(label="TL", column="try_kg")


def test_load_crops_rejects_missing_key(tmp_path):
    p = tmp_path / "crops.yml"
    p.write_text(
        "hazelnut:\n  slug: hazelnut\n  name: Hazelnut\n  exchanges: []\n"
        "  sections: []\n  analyses: []\n  range_currencies: []\n" + _LOCAL
    )
    with pytest.raises(ValueError, match="country"):
        load_crops(p)


def test_load_crops_rejects_slug_mismatch(tmp_path):
    p = tmp_path / "crops.yml"
    p.write_text(
        "fig:\n  slug: hazelnut\n  name: Fig\n  country: Turkey\n  exchanges: []\n"
        "  sections: []\n  analyses: []\n  range_currencies: []\n" + _LOCAL
    )
    with pytest.raises(ValueError, match="slug 'hazelnut' does not match"):
        load_crops(p)


_BASE = (
    "hazelnut:\n  slug: hazelnut\n  name: Hazelnut\n  country: Turkey\n  exchanges: []\n"
    "  sections: []\n  analyses: []\n  range_currencies: []\n"
)


def test_load_crops_rejects_missing_local_currency(tmp_path):
    p = tmp_path / "crops.yml"
    p.write_text(_BASE)
    with pytest.raises(ValueError, match="local_currency"):
        load_crops(p)


@pytest.mark.parametrize(
    "value",
    ["TL", "{label: TL}", "{column: try_kg}", "{label: TL, column: 3}", "{label: '', column: try_kg}"],
)
def test_load_crops_rejects_malformed_local_currency(tmp_path, value):
    p = tmp_path / "crops.yml"
    p.write_text(_BASE + f"  local_currency: {value}\n")
    with pytest.raises(ValueError, match="local_currency"):
        load_crops(p)


def test_local_currency_mom_key_follows_the_column():
    assert LocalCurrency("TL", "try_kg").mom_key == "try_mom"
    assert LocalCurrency("Rs", "inr_kg").mom_key == "inr_mom"

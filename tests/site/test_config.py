import pytest

from hazelnut.site.config import load_crops


def test_load_crops_reads_hazelnut():
    crop = load_crops()["hazelnut"]
    assert crop.country == "Turkey"
    assert crop.range_currencies == ("usd",)


def test_load_crops_rejects_missing_key(tmp_path):
    p = tmp_path / "crops.yml"
    p.write_text(
        "hazelnut:\n  slug: hazelnut\n  name: Hazelnut\n  exchanges: []\n"
        "  sections: []\n  analyses: []\n  range_currencies: []\n"
    )
    with pytest.raises(ValueError, match="country"):
        load_crops(p)


def test_load_crops_rejects_slug_mismatch(tmp_path):
    p = tmp_path / "crops.yml"
    p.write_text(
        "fig:\n  slug: hazelnut\n  name: Fig\n  country: Turkey\n  exchanges: []\n"
        "  sections: []\n  analyses: []\n  range_currencies: []\n"
    )
    with pytest.raises(ValueError, match="fig"):
        load_crops(p)

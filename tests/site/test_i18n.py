"""The active site language (hazelnut.site.i18n)."""

import pytest

from hazelnut.site import i18n


def test_english_by_default():
    assert i18n.lang() == "en"


@pytest.mark.parametrize("profile, expected", [
    ("tr", "tr"), ("en", "en"), ("preview,tr", "tr"), (" tr , preview", "tr"), ("preview", "en"),
])
def test_quarto_profile_sets_the_language(monkeypatch, profile, expected):
    monkeypatch.setenv("QUARTO_PROFILE", profile)
    assert i18n.lang() == expected


def test_site_lang_applies_outside_quarto(monkeypatch):
    monkeypatch.setenv("SITE_LANG", "tr")
    assert i18n.lang() == "tr"


def test_quarto_profile_wins_over_site_lang(monkeypatch):
    # A SITE_LANG left in the shell must not turn an English render Turkish.
    monkeypatch.setenv("QUARTO_PROFILE", "en")
    monkeypatch.setenv("SITE_LANG", "tr")
    assert i18n.lang() == "en"


def test_unknown_site_lang_is_an_error(monkeypatch):
    monkeypatch.setenv("SITE_LANG", "de")
    with pytest.raises(ValueError, match="SITE_LANG"):
        i18n.lang()

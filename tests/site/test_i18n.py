"""The active site language, its strings and its number and date formats
(hazelnut.site.i18n)."""

import pytest

from hazelnut.site import i18n


def test_english_by_default():
    assert i18n.lang() == "en"
    assert i18n.LANG == "en"


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


# --- t() --------------------------------------------------------------------------------

def test_t_fills_named_fields():
    assert i18n.t("format.month_year", month="October", year=2026) == "October 2026"


def test_t_leaves_plotly_placeholders_alone():
    hover = i18n.t("chart.price.local_hover", unit="TL")
    assert hover == "%{y:,.2f} TL/kg<extra></extra>"


def test_t_unknown_key_is_an_error():
    with pytest.raises(KeyError, match="no.such.key"):
        i18n.t("no.such.key")


def test_t_falls_back_to_english_for_a_todo_entry(turkish, monkeypatch):
    tr = dict(i18n.strings("tr"), **{"format.month_year": i18n.TODO})
    monkeypatch.setattr(i18n, "strings", lambda code: tr if code == "tr" else i18n._load("en"))
    assert i18n.t("format.month_year", month="Ekim", year=2026) == "Ekim 2026"


def test_template_fields():
    assert i18n.fields("{a} took %{y:.2f} of {b}, {a} %{x}") == {"a", "b", "x"}


def test_plural():
    assert i18n.plural("unit.months", 1) == "1 month"
    assert i18n.plural("unit.months", 14) == "14 months"


def test_join_names():
    assert i18n.join_names(["Italy"]) == "Italy"
    assert i18n.join_names(["Italy", "Germany"]) == "Italy and Germany"
    assert i18n.join_names(["A", "B", "C"]) == "A, B and C"


# --- key and field parity ---------------------------------------------------------------

def test_english_and_turkish_have_the_same_keys_and_fields():
    assert i18n.parity_problems(i18n.strings("en"), i18n.strings("tr")) == []


def test_parity_problems_name_the_key():
    en = {"a": "{x} and {y}", "b": "B", "c": "C {n}"}
    tr = {"a": "{x} ve {z}", "c": i18n.TODO, "d": "D"}
    assert i18n.parity_problems(en, tr) == [
        "a: fields differ (en {x, y}, tr {x, z})",
        "b: missing in tr",
        "d: not in en",
    ]


def test_turkish_todo_entries_fail_only_a_turkish_deploy(monkeypatch):
    tr = {"a": "A", "b": i18n.TODO}
    monkeypatch.delenv(i18n.DEPLOY_FLAG, raising=False)
    assert i18n.deploy_problems(tr) == []
    monkeypatch.setenv(i18n.DEPLOY_FLAG, "en")
    assert i18n.deploy_problems(tr) == []
    monkeypatch.setenv(i18n.DEPLOY_FLAG, "en,tr")
    assert i18n.deploy_problems(tr) == ["b: not translated (TODO) in tr"]
    assert i18n.deploy_problems(tr, deploying=["en"]) == []
    assert i18n.deploy_problems(tr, deploying=["en", "tr"]) == ["b: not translated (TODO) in tr"]


def test_no_untranslated_turkish_when_deploying_turkish():
    # Passes during development; with SITE_DEPLOY=en,tr it lists every TODO left in tr.yml.
    assert i18n.deploy_problems() == []


# --- formatters -------------------------------------------------------------------------

def test_english_formats():
    assert i18n.fmt_usd(4.128) == "$4.13"
    assert i18n.fmt_number(1234.5) == "1,234.50"
    assert i18n.fmt_tonnes(86440.4) == "86,440"
    assert i18n.fmt_pct(0.315, 1) == "31.5%"
    assert i18n.fmt_pct(0.8418) == "84%"
    assert i18n.fmt_pct(0.315, 1, signed=True) == "+31.5%"
    assert i18n.fmt_pct(-0.035, 1, signed=True) == "−3.5%"
    assert i18n.fmt_pct(0.0001, 1, signed=True) == "0.0%"
    assert i18n.fmt_signed(-0.1) == "−0.10"
    assert i18n.fmt_signed(0.001) == "0.00"
    assert i18n.month_name(10) == "October"
    assert i18n.month_name(10, short=True) == "Oct"
    assert i18n.month_label("2026-10") == "October 2026"
    assert i18n.month_label("2026") == "2026"


def test_turkish_formats(turkish):
    assert i18n.fmt_usd(4.128) == "4,13 $"
    assert i18n.fmt_number(4.128) == "4,13"
    assert i18n.fmt_number(1234.5) == "1.234,50"
    assert i18n.fmt_tonnes(86440) == "86.440"
    assert i18n.fmt_pct(0.315, 1) == "%31,5"
    assert i18n.fmt_pct(0.8418) == "%84"
    assert i18n.fmt_pct(-0.035, 1, signed=True) == "−%3,5"
    assert i18n.fmt_pct(0.315, 1, signed=True) == "+%31,5"
    assert i18n.fmt_signed(-0.1) == "−0,10"
    assert i18n.month_name(10) == "Ekim"
    assert i18n.month_name(10, short=True) == "Eki"
    assert i18n.month_label("2026-10") == "Ekim 2026"


@pytest.mark.parametrize("fn", [i18n.fmt_usd, i18n.fmt_number, i18n.fmt_tonnes, i18n.fmt_pct,
                                i18n.fmt_signed])
def test_missing_values_show_n_a(fn):
    assert fn(None) == "n/a"
    assert fn(float("nan")) == "n/a"


def test_as_of_stamp_in_turkish(turkish):
    assert i18n.as_of({"as_of": "2026-10"}).startswith("Veriler Ekim 2026 itibarıyla")


def test_plotly_locale():
    assert i18n.plotly_locale() == {"locale": "en", "separators": ".,"}


def test_plotly_locale_in_turkish_matches_plotlys_tr_locale(turkish):
    from hazelnut.site.plotly_locales import LOCALES

    fmt = LOCALES["tr"]["format"]
    assert i18n.plotly_locale() == {"locale": "tr", "separators": fmt["decimal"] + fmt["thousands"]}
    assert [i18n.month_name(m, short=True) for m in range(1, 13)] == fmt["shortMonths"]
    assert [i18n.month_name(m) for m in range(1, 13)] == fmt["months"]


def test_english_crop_names_match_crops_yml():
    from hazelnut.site.config import load_crops

    for crop in load_crops().values():
        assert i18n.t(f"crop.{crop.slug}.name") == crop.name
        assert i18n.t(f"crop.{crop.slug}.country") == crop.country

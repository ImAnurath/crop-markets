"""Behaviour of the language JavaScript, run under Node against a stub browser
(tests/site/lang_js_harness.js): the first-visit detection (site/filters/lang-detect.js)
and the switch in site/assets/site.js. Skipped when node is not installed."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hazelnut.site.config import SITE_DIR

NODE = shutil.which("node")
HARNESS = Path(__file__).with_name("lang_js_harness.js")
DETECT = SITE_DIR / "filters" / "lang-detect.js"
SITE_JS = SITE_DIR / "assets" / "site.js"
KEY = "crop-markets-lang"
EN_PAGE = "https://example.org/crop-markets/hazelnut/analyses/exports.html"
TR_PAGE = "https://example.org/crop-markets/tr/hazelnut/analyses/exports.html"
ALTERNATES = {"en": "../../hazelnut/analyses/exports.html",  # as seen from the page itself
              "tr": "../../tr/hazelnut/analyses/exports.html",
              "x-default": "../../hazelnut/analyses/exports.html"}
TR_FIRST = ["tr-TR", "tr", "en"]

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run(script: Path, **case) -> dict:
    case = {"lang": "en", "url": EN_PAGE, "alternates": ALTERNATES, "storage": "real",
            "languages": TR_FIRST, **case}
    done = subprocess.run([NODE, str(HARNESS), str(script), json.dumps(case)],
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def detect(**case) -> dict:
    return run(DETECT, **case)


def test_turkish_first_browser_goes_to_the_turkish_page_once_keeping_query_and_hash():
    out = detect(url=EN_PAGE + "?x=1#top")
    assert out["replaced"] == TR_PAGE + "?x=1#top"
    assert out["stored"] == "tr"  # so the next English page does not redirect


@pytest.mark.parametrize("languages, redirects", [
    (["de", "tr", "en"], True),
    (["tr"], True),
    (["en", "tr"], False),
    (["en-GB", "tr-TR"], False),
    (["de", "fr"], False),
    ([], False),
])
def test_redirects_only_when_turkish_comes_before_english(languages, redirects):
    out = detect(languages=languages)
    assert (out["replaced"] is not None) is redirects
    assert out["stored"] == ("tr" if redirects else None)


@pytest.mark.parametrize("stored", ["en", "tr"])
def test_a_stored_choice_is_never_overridden(stored):
    # "en": someone who chose English with the switch is not sent back to Turkish.
    out = detect(stored={KEY: stored})
    assert out["replaced"] is None and out["stored"] == stored


@pytest.mark.parametrize("storage", ["throws", "shim"])
def test_no_redirect_without_working_storage(storage):
    # Blocked storage, or the colour-scheme shim's memory store that forgets on every
    # load: the switch's choice could not be kept, so a redirect would trap the visitor.
    assert detect(storage=storage)["replaced"] is None


def test_turkish_pages_never_redirect():
    out = detect(lang="tr", url=TR_PAGE, alternates={  # Turkish-first browser, nothing stored
        "en": "../../../hazelnut/analyses/exports.html", "tr": "exports.html"})
    assert out["replaced"] is None and out["stored"] is None


def test_no_redirect_without_a_turkish_counterpart():  # the 404 page
    assert detect(alternates={})["replaced"] is None


STRINGS = {"theme-toggle": "Switch light / dark", "lang-switch": {"label": "Language", "langs": [
    {"lang": "tr", "code": "TR", "title": "Bu sayfayı Türkçe okuyun"},
    {"lang": "en", "code": "EN", "title": "Read this page in English"}]}}


def test_switch_on_an_english_page_links_the_turkish_one_and_stores_the_choice():
    out = run(SITE_JS, url=EN_PAGE + "?x=1", strings=STRINGS, clickAfterHash="#later",
              languages=["en"])
    sw = out["switch"]
    assert sw["label"] == "Language" and sw["themeTitle"] == "Switch light / dark"
    assert [(i["tag"], i["text"], i["current"]) for i in sw["items"]] == [
        ("A", "TR", None), ("SPAN", "EN", "true")]
    assert sw["items"][0]["lang"] == "tr" and sw["items"][0]["title"] == "Bu sayfayı Türkçe okuyun"
    assert sw["hrefAfterHashchange"] == sw["clickedHref"] == TR_PAGE + "?x=1#later"
    assert out["stored"] == "tr"


def test_switch_on_a_turkish_page_leads_back_to_english_and_stores_it():
    strings = {**STRINGS, "theme-toggle": "Açık / koyu tema"}
    out = run(SITE_JS, lang="tr", url=TR_PAGE + "#a", strings=strings, clickAfterHash="#b",
              alternates={"en": "../../../hazelnut/analyses/exports.html", "tr": "exports.html"})
    sw = out["switch"]
    assert sw["themeTitle"] == "Açık / koyu tema"
    assert [(i["tag"], i["text"]) for i in sw["items"]] == [("SPAN", "TR"), ("A", "EN")]
    assert sw["clickedHref"] == EN_PAGE + "#b"
    assert out["stored"] == "en"  # and detection then leaves English pages alone:
    assert detect(stored={KEY: "en"})["replaced"] is None


@pytest.mark.parametrize("event", ["click", "auxclick"])
def test_switch_stores_the_choice_on_a_middle_click_too(event):
    # A middle-click (auxclick) opens the other language in a new tab: that is a choice too.
    out = run(SITE_JS, strings=STRINGS, clickAfterHash="", clickEvent=event, languages=["en"])
    assert out["switch"]["clickedHref"] == TR_PAGE
    assert out["stored"] == "tr"


def test_switch_works_with_blocked_storage_and_is_absent_without_a_counterpart():
    out = run(SITE_JS, strings=STRINGS, storage="throws", clickAfterHash="")
    assert out["switch"]["clickedHref"] == TR_PAGE and out["stored"] == "THREW"
    assert run(SITE_JS, strings=STRINGS, alternates={})["switch"] is None


def test_a_chart_that_cannot_load_says_so_in_the_pages_language():
    # The words come from the page's strings block, so site.js holds no visible text.
    out = run(SITE_JS, lang="tr", url=TR_PAGE, chart=True,
              strings={**STRINGS, "chart-failed": "Bu grafik yüklenemedi."})
    assert out["chart"] == {"requested": "https://cdn.example/plotly.min.js",
                            "text": "Bu grafik yüklenemedi."}
    assert run(SITE_JS, chart=True, strings=STRINGS)["chart"]["text"] == ""

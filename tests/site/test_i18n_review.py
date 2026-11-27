"""scripts/i18n_review.py: the owner's English | Turkish review pack.

The pack (site/_site/i18n-review.html) is a local file for the owner only: it is written
after a render, never linked from the site, never in a sitemap and never deployed.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

from hazelnut.site import i18n
from hazelnut.site.config import SITE_DIR

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
RENDERED = SITE_DIR / "_site"
WORKFLOWS = REPO / ".github" / "workflows"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def review():
    return _load("i18n_review")


# --- t() strings -------------------------------------------------------------------------

def test_collects_every_key_once_in_file_order(review):
    en, tr = i18n.strings("en"), i18n.strings("tr")
    rows = review.collect_keys(en, tr)
    assert len(rows) == len(en)
    assert [r["key"] for r in rows] == list(en)
    assert [r["id"] for r in rows] == list(range(1, len(en) + 1))
    assert all(r["tr"] == tr[r["key"]] for r in rows)


def test_every_key_lands_in_a_known_group(review):
    groups = {g for g, _ in review.GROUPS}
    for key in i18n.strings("en"):
        assert review.key_group(key) in groups, key


def test_key_groups_follow_the_prefix(review):
    assert review.key_group("hazelnut.analyses.forecasting.h1") == "forecasting"
    assert review.key_group("hazelnut.analyses.crop_and_frost.found") == "crop-and-frost"
    assert review.key_group("home.crop_price") == "home"
    assert review.key_group("explorer.ui.about.title") == "explorer"
    assert review.key_group("country.cyprus") == "countries"
    assert review.key_group("hazelnut.column.usd_try") == "workbook"
    assert review.key_group("chart.window.y5") == "charts"
    assert review.key_group("something.new") == "shared"


def test_placeholders_are_marked_after_escaping(review):
    out = review.mark("{name} took <b>{pct}</b> & %{y:.2f}")
    assert '<span class="ph">{name}</span>' in out
    assert '<span class="ph">%{y:.2f}</span>' in out
    assert "&lt;b&gt;" in out and "&amp;" in out and "<b>" not in out


# --- prose blocks ------------------------------------------------------------------------

QMD = '''---
title: "T"
title-tr: "T tr"
description: "D"
description-tr: "D tr"
---

::: {.wrap}
::: {.content-visible when-profile="en"}
# Hello *there*

::: {.lede}
Some text {{< var author_bio >}}.
:::
:::

::: {.content-visible when-profile="tr"}
# Merhaba

```{python}
ph.raw_html(f"""
<section><h3>Başlık</h3><p>Bir & iki {ph.escape(x)}</p></section>
::: not a fence inside code
""")
```
:::
:::

::: {lang="en" data-title="x"}
Only English here.
:::
'''


def test_prose_blocks_handle_nesting_code_and_lang_divs(review):
    blocks = review.prose_blocks(QMD)
    assert [(b["lang"], b["line"]) for b in blocks] == [("en", 9), ("tr", 17), ("en", 29)]
    assert "Some text" in blocks[0]["src"] and ":::" in blocks[0]["src"]  # inner lede kept
    assert "not a fence inside code" in blocks[1]["src"]


def test_prose_pairs_report_unequal_counts(review):
    pairs, n_en, n_tr = review.prose_pairs(QMD)
    assert (n_en, n_tr) == (2, 1)
    assert len(pairs) == 2 and pairs[1][1] is None


def test_prose_text_is_readable(review):
    blocks = review.prose_blocks(QMD)
    tr_text = review.prose_text(blocks[1]["src"])
    assert "ph.raw_html" not in tr_text and "```" not in tr_text and "<h3>" not in tr_text
    assert "Başlık" in tr_text and "Bir & iki {ph.escape(x)}" in tr_text
    en_text = review.prose_text(blocks[0]["src"])
    assert "{{< var author_bio >}}" in en_text  # shortcodes survive the tag stripping
    assert review.prose_text("5 < 6 & 7 > 3") == "5 < 6 & 7 > 3"


def test_front_matter(review):
    assert review.front_matter(QMD) == {"title": "T", "title-tr": "T tr",
                                        "description": "D", "description-tr": "D tr"}


def test_every_site_page_has_as_many_turkish_blocks_as_english(review):
    problems = review.prose_mismatches(SITE_DIR)
    assert problems == [], "\n".join(problems)
    assert sum(review.prose_pairs((SITE_DIR / p["qmd"]).read_text(encoding="utf-8"))[1]
               for p in review.PAGES if (SITE_DIR / p["qmd"]).is_file()) > 20


# --- questions ---------------------------------------------------------------------------

def test_questions_cite_only_existing_keys(review):
    questions = review.load_questions()
    assert 1 <= len(questions) <= 14  # the leftovers only: the owner asked for fewer
    en = i18n.strings("en")
    for q in questions:
        assert q.get("title") and q.get("suggest"), q
        for key in q.get("keys", []):
            assert key in en, f"{q['title']}: unknown key {key}"


def test_author_bio_tr_question_is_listed(review):
    text = " ".join(str(q) for q in review.load_questions())
    assert "author_bio_tr" in text
    assert "Türkiye tarım ürünleri piyasalarının veri analizi." in text


# --- the pack ----------------------------------------------------------------------------

def _tiny(tmp_path):
    src = tmp_path / "src"
    (src / "hazelnut").mkdir(parents=True)
    (src / "index.qmd").write_text(
        '---\ntitle: "<i>Home</i>"\n---\n\n'
        '::: {.content-visible when-profile="en"}\nA <script>alert(1)</script> 5 < 6 & ok\n:::\n\n'
        '::: {.content-visible when-profile="tr"}\nBir "ev"\n:::\n', encoding="utf-8")
    site = tmp_path / "_site"
    (site / "tr").mkdir(parents=True)
    (site / "tr" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (site / "index.html").write_text("<p>x</p>", encoding="utf-8")
    return src, site


def test_pack_escapes_html(review, tmp_path):
    src, site = _tiny(tmp_path)
    out = site / review.REVIEW_PAGE
    en = {"a.b": "<script>alert('x')</script> & {n}", "home.c": "plain"}
    tr = {"a.b": "<img src=x onerror=y> & {n}", "home.c": "düz"}
    stats = review.build(site, out, src_dir=src, en=en, tr=tr, questions=[
        {"title": "Q <b>", "keys": ["a.b"], "en": "<u>", "tr": "<s>", "suggest": "use `x<y`"}])
    page = out.read_text(encoding="utf-8")
    assert "<script>alert" not in page and "<img src=x" not in page
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in page
    assert "&lt;img src=x onerror=y&gt;" in page
    assert "Q &lt;b&gt;" in page and "<code>x&lt;y</code>" in page
    assert "5 &lt; 6 &amp; ok" in page and "&lt;i&gt;Home&lt;/i&gt;" in page
    assert stats["keys"] == 2 and stats["questions"] == 1
    assert stats["prose"]["index.qmd"] == (1, 1)


def test_pack_is_self_contained(review, tmp_path):
    src, site = _tiny(tmp_path)
    out = site / review.REVIEW_PAGE
    review.build(site, out, src_dir=src, en={"x": "y"}, tr={"x": "z"}, questions=[])
    page = out.read_text(encoding="utf-8")
    assert not re.search(r"""(?:src|href)\s*=\s*["'](?:https?:)?//""", page)
    assert "<link" not in page and "@import" not in page and "<script" not in page
    assert "prefers-color-scheme: dark" in page
    assert 'name="viewport"' in page and 'content="noindex' in page


def test_main_needs_both_rendered_trees(review, tmp_path, capsys):
    site = tmp_path / "_site"
    site.mkdir()
    (site / "index.html").write_text("<p>x</p>", encoding="utf-8")
    assert review.main(["--site-dir", str(site)]) == 2
    assert "render both languages" in capsys.readouterr().err
    assert not (site / review.REVIEW_PAGE).exists()


@pytest.mark.skipif(not (RENDERED / "tr" / "index.html").is_file(),
                    reason="site/_site/tr not rendered (run scripts/render_site.py)")
def test_pack_from_the_rendered_site(review, tmp_path, capsys):
    out = tmp_path / review.REVIEW_PAGE
    assert review.main(["--out", str(out)]) == 0
    page = out.read_text(encoding="utf-8")
    en = i18n.strings("en")
    assert len(re.findall(r'<tr class="row key" id="k\d+"', page)) == len(en)
    assert f'id="k{len(en)}"' in page and 'id="q1"' in page
    for heading in ("Questions for the owner", "Forecasting", "Navbar, footer", "Workbook",
                    "Glossary"):
        assert heading in page, heading
    assert "author_bio_tr" in page
    assert "Hazelnut market data (Turkey)" in page  # the workbooks' README text
    printed = capsys.readouterr().out
    assert f"keys: {len(en)}" in printed and "mismatches: none" in printed


# --- changed since the review ------------------------------------------------------------

def _sources(en, tr, index="", tr_profile=""):
    return {"en": en, "tr": tr, "pages": {"index.qmd": index},
            "profiles": {"_quarto-en.yml": "", "_quarto-tr.yml": tr_profile}}


def test_changes_list_every_differing_row_with_its_pack_id(review):
    prose = ('---\ntitle: "Home"\ntitle-tr: "{t}"\n---\n\n'
             '::: {{.content-visible when-profile="en"}}\nHello\n:::\n\n'
             '::: {{.content-visible when-profile="tr"}}\n{p}\n:::\n')
    base = _sources({"a": "A", "b": "B {n}"}, {"a": "Ä", "b": "eski {n}"},
                    prose.format(t="Eski", p="Merhaba"), "website:\n  title: Crop Markets\n")
    now = _sources({"a": "A", "b": "B {n}", "c": "C"}, {"a": "Ä", "b": "yeni {n}", "c": "Ç"},
                   prose.format(t="Yeni", p="Merhaba"), "website:\n  title: Ürün Piyasaları\n")
    rows = review.changes(base, now)
    assert [(r["id"], r["label"]) for r in rows] == [
        ("#2", "b"), ("#3", "c"), ("M1", "Home: title"), ("N1", "website.title")]
    assert rows[0]["en"] == ("B {n}", "B {n}") and rows[0]["tr"] == ("eski {n}", "yeni {n}")
    assert rows[1]["tr"] == (None, "Ç")  # a new key
    html_ = review.changes_html(rows)
    assert '<a href="#k2">#2</a>' in html_ and '<a href="#m1">M1</a>' in html_
    assert "<del>eski <span class=\"ph\">{n}</span></del>" in html_
    assert "(unchanged)" in html_ and "(new)" in html_
    assert review.changes(base, base) == []


def test_pack_puts_the_changes_right_after_the_questions(review, tmp_path):
    src, site = _tiny(tmp_path)
    out = site / review.REVIEW_PAGE
    rows = [{"id": "#1", "anchor": "k1", "label": "x", "en": ("y", "y"), "tr": ("a", "b")}]
    stats = review.build(site, out, src_dir=src, en={"x": "y"}, tr={"x": "b"}, questions=[],
                         changed=rows)
    page = out.read_text(encoding="utf-8")
    assert stats["changed"] == 1
    assert page.index('id="questions"') < page.index('id="changed"') < page.index('id="page-home"')
    assert "Changed since your review (1)" in page and "<ins>b</ins>" in page
    review.build(site, out, src_dir=src, en={"x": "y"}, tr={"x": "b"}, questions=[])
    assert "cannot be listed" in out.read_text(encoding="utf-8")  # no baseline for a tmp site


def test_changes_since_the_reviewed_commit(review):
    base = review.load_base()
    if base is None:
        pytest.skip("no git history here")
    rows = {r["label"]: r for r in review.changes(base, review.current_sources())}
    assert rows["dashboard.h1"]["tr"][0] == "Fiyat ve onun hakkında dürüstçe söyleyebileceklerimiz"
    assert rows["na"]["en"] == ("n/a", "N/A") and rows["na"]["tr"] == ("yok", "N/A")
    assert "website.title" in rows  # the Turkish brand


# --- kept out of the deploy --------------------------------------------------------------

def test_render_site_never_writes_the_pack(review, tmp_path, monkeypatch):
    render_site = _load("render_site")
    site = tmp_path / "site"
    (site / "_site" / "tr").mkdir(parents=True)
    monkeypatch.setattr(render_site, "SITE", site)
    monkeypatch.setattr(render_site.subprocess, "run",
                        lambda cmd, env: subprocess.CompletedProcess(cmd, 0))
    assert render_site.main([]) == 0
    assert not list(site.rglob(review.REVIEW_PAGE))
    assert "i18n_review" not in (SCRIPTS / "render_site.py").read_text(encoding="utf-8")


def test_pack_in_the_site_dir_is_not_counted_as_a_page(review, tmp_path):
    from tests.site.test_site_trees import unpaired_pages
    snapshot = _load("snapshot_text")
    for rel in ("index.html", "tr/index.html", review.REVIEW_PAGE):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("<p>x</p>", encoding="utf-8")
    assert unpaired_pages(tmp_path) == []
    assert sorted(snapshot.site_texts(tmp_path)) == ["index.txt"]


def test_workflows_never_run_the_review_script():
    for wf in WORKFLOWS.glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        assert "i18n_review" not in text and "i18n-review" not in text, wf.name


@pytest.mark.skipif(not RENDERED.is_dir(), reason="site/_site not rendered")
def test_built_site_never_links_the_pack(review):
    bad = []
    for path in RENDERED.rglob("*"):
        if path.suffix not in (".html", ".xml", ".txt", ".json") or path.name == review.REVIEW_PAGE:
            continue
        if review.REVIEW_PAGE in path.read_text(encoding="utf-8", errors="replace"):
            bad.append(path.relative_to(RENDERED).as_posix())
    assert bad == []

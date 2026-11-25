"""Write the owner's English | Turkish review pack: one self-contained HTML page.

The pack shows, side by side and grouped by page:
  1. the open questions for the owner (scripts/i18n_review_questions.yml);
  2. every page's title and description (front matter) and every prose block
     (``when-profile="en"`` / ``"tr"`` pairs, and the 404 page's ``lang`` blocks);
  3. every ``t()`` string of site/i18n/en.yml and tr.yml, numbered in en.yml order,
     with one example as rendered on the site where one is found;
  4. the navbar, footer and site strings of the two profiles;
  5. the workbooks' sheet names, headers and text cells;
  6. the glossary, for reference.
Every row has an id (Q, #, M, P, N, W) so the owner can answer by id.

The pack is for the owner only. It is written after a render into site/_site/, is not
linked from any page or sitemap, and is never deployed: the workflow does not run this
script and site/_site is not in git (a full English render also deletes it).

Usage (render both languages first: scripts/render_site.py):
    python scripts/i18n_review.py            # writes site/_site/i18n-review.html
    python scripts/i18n_review.py --out PATH
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import re
import sys
from itertools import zip_longest
from pathlib import Path

import yaml

from hazelnut.site import i18n

HERE = Path(__file__).resolve().parent
SITE = HERE.parent / "site"
REVIEW_PAGE = "i18n-review.html"
QUESTIONS = HERE / "i18n_review_questions.yml"

# Pages in site order: (group id, heading, source, rendered page).
PAGES = [
    {"id": "home", "title": "Home", "qmd": "index.qmd"},
    {"id": "overview", "title": "Hazelnut overview", "qmd": "hazelnut/index.qmd"},
    {"id": "dashboard", "title": "Dashboard", "qmd": "hazelnut/dashboard.qmd"},
    {"id": "analyses", "title": "Analyses (index)", "qmd": "hazelnut/analyses/index.qmd"},
    {"id": "seasonality", "title": "Seasonality", "qmd": "hazelnut/analyses/seasonality.qmd"},
    {"id": "exports", "title": "Exports", "qmd": "hazelnut/analyses/exports.qmd"},
    {"id": "crop-and-frost", "title": "Crop and frost",
     "qmd": "hazelnut/analyses/crop-and-frost.qmd"},
    {"id": "exchanges", "title": "Exchanges", "qmd": "hazelnut/analyses/exchanges.qmd"},
    {"id": "forecasting", "title": "Forecasting", "qmd": "hazelnut/analyses/forecasting.qmd"},
    {"id": "explorer", "title": "Data explorer", "qmd": "hazelnut/explorer.qmd"},
    {"id": "methods", "title": "Methods", "qmd": "methods.qmd"},
    {"id": "downloads", "title": "Downloads", "qmd": "downloads.qmd"},
    {"id": "404", "title": "404 page (one page, both languages)", "qmd": "404.qmd"},
]
SHARED = [
    ("findings", "Shared: findings sentences (dashboard and analysis pages)"),
    ("charts", "Shared: charts and method names"),
    ("formats", "Shared: formats, months, units, stamp and small words"),
    ("workbook", "Workbook and sources (strings)"),
    ("countries", "Country names (exports chart and workbook)"),
    ("shared", "Other shared strings"),
]
GROUPS = [(p["id"], p["title"]) for p in PAGES] + SHARED

# Key prefix (a whole key or a key path) -> group; the longest match wins.
# hazelnut.analyses.<slug>.* goes to that analysis page.
PREFIXES = {
    "home": "home", "overview": "overview", "strip": "overview",
    "dashboard": "dashboard", "hazelnut.dashboard": "dashboard",
    "analyses": "analyses", "explorer": "explorer", "downloads": "downloads",
    "methods_page": "methods",
    **{p: "findings" for p in (
        "forecast", "scoreboard", "lira", "frost", "crop_price", "gap", "exports",
        "crop_check", "crop_estimate", "price", "range", "season", "seasonality",
        "exchanges", "crop_source", "hazelnut.timing_note")},
    **{p: "charts" for p in ("chart", "hazelnut.chart", "method", "unit")},
    **{p: "formats" for p in (
        "na", "format", "month", "month_short", "span", "count_word", "list", "table",
        "panel", "stamp", "crop")},
    **{p: "workbook" for p in (
        "workbook", "hazelnut.column", "hazelnut.sheet", "hazelnut.source",
        "hazelnut.product", "sources")},
    "country": "countries",
}
PAGE_IDS = {p["id"] for p in PAGES}


def _snapshot():
    """scripts/snapshot_text.py (the visible-text extractor the English gate uses)."""
    spec = importlib.util.spec_from_file_location("snapshot_text", HERE / "snapshot_text.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- t() strings -------------------------------------------------------------------------

def key_group(key: str) -> str:
    parts = key.split(".")
    if len(parts) > 3 and parts[0] == "hazelnut" and parts[1] == "analyses":
        slug = parts[2].replace("_", "-")
        if slug in PAGE_IDS:
            return slug
    best = ""
    for prefix in PREFIXES:
        if (key == prefix or key.startswith(prefix + ".")) and len(prefix) > len(best):
            best = prefix
    return PREFIXES[best] if best else "shared"


def collect_keys(en: dict[str, str], tr: dict[str, str]) -> list[dict]:
    """Every English key in file order, numbered from 1, with its Turkish and its group."""
    return [{"id": n, "key": k, "en": v, "tr": tr.get(k, ""), "group": key_group(k)}
            for n, (k, v) in enumerate(en.items(), 1)]


_FIELD = re.compile(r"\{(\w+)\}")


def _parts(template: str) -> list[str] | None:
    """The literal pieces of a template with fields (None if not worth searching for)."""
    if "%{" in template or "<" in template or not _FIELD.search(template):
        return None
    parts = _FIELD.split(template)[0::2]
    if sum(ch.isalpha() for p in parts for ch in p) < 8:
        return None
    return parts


def _find(parts: list[str], line: str) -> bool:
    """True when the literal pieces occur in order on the line, each field 1-160 chars."""
    lits = [(i, p) for i, p in enumerate(parts) if p]
    start = 0
    while True:
        first = line.find(lits[0][1], start)
        if first < 0:
            return False
        pos, prev_i, ok = first + len(lits[0][1]), lits[0][0], True
        for i, lit in lits[1:]:
            nxt = line.find(lit, pos + (i - prev_i > 0))
            if nxt < 0 or nxt - pos > 160 * (i - prev_i):
                ok = False
                break
            pos, prev_i = nxt + len(lit), i
        if ok:
            return True
        start = first + 1


def examples(rows: list[dict], texts: dict[str, list[tuple[str, str]]]) -> dict:
    """{(key, lang): (page, line)}: one rendered line per template with fields."""
    out = {}
    for row in rows:
        for lang in ("en", "tr"):
            parts = _parts(row[lang])
            if not parts:
                continue
            longest = max(parts, key=len)
            for page, text in texts.get(lang, []):
                if longest not in text:
                    continue
                hit = next((ln for ln in text.splitlines() if longest in ln and _find(parts, ln)),
                           None)
                if hit:
                    out[(row["key"], lang)] = (page, hit if len(hit) <= 400 else hit[:397] + "…")
                    break
    return out


def rendered_texts(site_dir: Path) -> dict[str, list[tuple[str, str]]]:
    """Visible text of every rendered page, per language tree."""
    snap = _snapshot()
    texts: dict[str, list[tuple[str, str]]] = {"en": [], "tr": []}
    for path in sorted(Path(site_dir).rglob("*.html")):
        rel = path.relative_to(site_dir).as_posix()
        if path.name == REVIEW_PAGE:
            continue
        lang = "tr" if rel.startswith("tr/") else "en"
        texts[lang].append((rel, snap.page_text(path.read_text(encoding="utf-8"))))
    return texts


# --- prose blocks ------------------------------------------------------------------------

_DIV_OPEN = re.compile(r"^(:{3,})\s*(\{.*\}|[^\s{:].*)$")
_DIV_CLOSE = re.compile(r"^:{3,}\s*$")
_CODE = re.compile(r"^(`{3,}|~{3,})")
_LANG = re.compile(r"""(?:when-profile|(?<![\w-])lang)\s*=\s*["'](en|tr)["']""")


def prose_blocks(text: str) -> list[dict]:
    """Every fenced div of one language (when-profile or lang attribute), in file order:
    {"lang", "line" (1-based, the opening fence), "src" (the lines inside)}."""
    lines = text.splitlines()
    stack: list[tuple[int, str | None]] = []
    blocks, fence = [], None
    for i, raw in enumerate(lines):
        s = raw.strip()
        code = _CODE.match(s)
        if fence:
            if code and code.group(1)[0] == fence[0] and len(code.group(1)) >= len(fence) \
                    and s == code.group(1):
                fence = None
            continue
        if code:
            fence = code.group(1)
        elif _DIV_CLOSE.match(s):
            if stack:
                start, lang = stack.pop()
                if lang:
                    blocks.append({"lang": lang, "line": start + 1,
                                   "src": "\n".join(lines[start + 1:i])})
        elif (m := _DIV_OPEN.match(s)):
            lang = _LANG.search(m.group(2))
            stack.append((i, lang.group(1) if lang else None))
    return sorted(blocks, key=lambda b: b["line"])


def prose_pairs(text: str) -> tuple[list[tuple[dict | None, dict | None]], int, int]:
    """English and Turkish blocks paired in order, and how many of each there are."""
    blocks = prose_blocks(text)
    en = [b for b in blocks if b["lang"] == "en"]
    tr = [b for b in blocks if b["lang"] == "tr"]
    return list(zip_longest(en, tr)), len(en), len(tr)


def _qmds(src_dir: Path) -> list[Path]:
    skip = {"_site", ".quarto", "_freeze"}
    return sorted(p for p in Path(src_dir).rglob("*.qmd")
                  if not skip & set(p.relative_to(src_dir).parts))


def prose_mismatches(src_dir: Path) -> list[str]:
    """Source files whose English and Turkish block counts differ."""
    out = []
    for path in _qmds(src_dir):
        _, n_en, n_tr = prose_pairs(path.read_text(encoding="utf-8"))
        if n_en != n_tr:
            out.append(f"{path.relative_to(src_dir).as_posix()}: en={n_en} tr={n_tr}")
    return out


_SHORTCODE = re.compile(r"\{\{<.*?>\}\}")
_AUTOLINK = re.compile(r"<https?://[^>\s]+>")
_LI = re.compile(r"<li\b[^<>]*>", re.I)
_BLOCK_TAG = re.compile(r"</?(?:p|h[1-6]|li|ul|ol|div|section|table|tr|br|aside)\b[^<>]*>", re.I)
_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
_PY_WRAP = re.compile(r'^(?:ph\.raw_html\(f?(?:"""|\'\'\')|(?:"""|\'\'\')\))$')


def prose_text(src: str) -> str:
    """A prose block as readable text: code fences, div fences and HTML tags dropped (block
    tags become line breaks), entities decoded; shortcodes and {fields} kept."""
    kept = [ln for ln in src.splitlines()
            if not _CODE.match(ln.strip()) and not _PY_WRAP.match(ln.strip())
            and not _DIV_CLOSE.match(ln.strip()) and not _DIV_OPEN.match(ln.strip())]
    text = "\n".join(kept)
    saved: dict[str, str] = {}

    def protect(m):
        token = f"\x00{len(saved)}\x00"
        saved[token] = m.group(0)
        return token

    text = _AUTOLINK.sub(protect, _SHORTCODE.sub(protect, text))
    text = _BLOCK_TAG.sub("\n", _LI.sub("\n• ", text))
    text = html.unescape(_TAG.sub("", text))
    for token, value in saved.items():
        text = text.replace(token, value)
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def front_matter(text: str) -> dict[str, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    data = (yaml.safe_load(m.group(1)) or {}) if m else {}
    return {k: str(v) for k, v in data.items()
            if k in ("title", "title-tr", "description", "description-tr")}


# --- profiles, workbooks, glossary, questions --------------------------------------------

def _flat(node, path="", out=None) -> dict[str, str]:
    out = {} if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            _flat(v, f"{path}.{k}" if path else str(k), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _flat(v, f"{path}[{i}]", out)
    elif node is not None:
        out[path] = str(node)
    return out


def profile_rows(src_dir: Path) -> list[tuple[str, str, str]]:
    """(path, English, Turkish) for every value of the two language profiles."""
    def load(name):
        p = Path(src_dir) / name
        return _flat(yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}
    en, tr = load("_quarto-en.yml"), load("_quarto-tr.yml")
    paths = list(en) + [p for p in tr if p not in en]
    return [(p, en.get(p, ""), tr.get(p, "")) for p in paths]


def workbook_rows(downloads: Path, cap: int = 80) -> list[dict]:
    """Per workbook pair (<slug>-market-data.xlsx / -tr.xlsx): sheet names, then each
    sheet's distinct text cells (headers, README, sources, labels) as English | Turkish."""
    from openpyxl import load_workbook

    out = []
    for en_path in sorted(Path(downloads).glob("*.xlsx")):
        tr_path = en_path.with_name(en_path.stem + "-tr.xlsx")
        if en_path.stem.endswith("-tr") or not tr_path.is_file():
            continue
        en_wb = load_workbook(en_path, read_only=True)
        tr_wb = load_workbook(tr_path, read_only=True)
        sheets = []
        for en_ws, tr_ws in zip_longest(en_wb.worksheets, tr_wb.worksheets):
            pairs, seen, more = [], set(), 0
            if en_ws is not None and tr_ws is not None:
                for en_row, tr_row in zip(en_ws.iter_rows(values_only=True),
                                          tr_ws.iter_rows(values_only=True)):
                    for a, b in zip_longest(en_row, tr_row):
                        if not (isinstance(a, str) and any(ch.isalpha() for ch in a)):
                            continue
                        pair = (a, "" if b is None else str(b))
                        if pair in seen:
                            continue
                        seen.add(pair)
                        if len(pairs) < cap:
                            pairs.append(pair)
                        else:
                            more += 1
            sheets.append({"en": en_ws.title if en_ws else "", "tr": tr_ws.title if tr_ws else "",
                           "pairs": pairs, "more": more})
        en_wb.close()
        tr_wb.close()
        out.append({"en": en_path.name, "tr": tr_path.name, "sheets": sheets})
    return out


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []


# --- HTML --------------------------------------------------------------------------------

_MARK = re.compile(r"\{\{&lt;.*?&gt;\}\}|`\{python\}[^`]*`|%\{[^{}]*\}|\{[^{}\n]{1,80}\}")


def mark(text: str) -> str:
    """Escaped text with placeholders ({field}, %{plotly}, shortcodes, inline code) marked."""
    return _MARK.sub(lambda m: f'<span class="ph">{m.group(0)}</span>', html.escape(str(text)))


def rich(text: str) -> str:
    """Escaped text with `code` spans and marked placeholders."""
    out = _MARK.sub(lambda m: f'<span class="ph">{m.group(0)}</span>', html.escape(str(text)))
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", out)


def _inline_md(text: str) -> str:
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text))
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)


def glossary_html(md: str) -> str:
    """The glossary's Markdown (headings, paragraphs, lists, pipe tables) as HTML."""
    out, i, lines = [], 0, md.splitlines()
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            head, *body = rows
            out.append('<table class="gloss"><thead><tr>'
                       + "".join(f"<th>{_inline_md(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in r) + "</tr>"
                                 for r in body) + "</tbody></table>")
            continue
        if (m := re.match(r"(#{1,6})\s+(.*)", line)):
            level = min(len(m.group(1)) + 2, 6)
            out.append(f"<h{level}>{_inline_md(m.group(2))}</h{level}>")
        elif line.startswith(("- ", "* ")):
            items = []
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                items.append(f"<li>{_inline_md(lines[i].strip()[2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif line:
            out.append(f"<p>{_inline_md(line)}</p>")
        i += 1
    return "\n".join(out)


def _row(rid: str, anchor: str, label: str, en: str, tr: str, *, cls: str = "row",
         en_eg=None, tr_eg=None, raw: bool = False) -> str:
    def cell(lang, text, eg):
        body = text if raw else (mark(text) if text else '<span class="none">(none)</span>')
        if eg:
            body += f'<div class="eg"><span>on {html.escape(eg[0])}:</span> {html.escape(eg[1])}</div>'
        return f'<td class="{lang}" lang="{lang}" data-l="{lang.upper()}">{body}</td>'
    same = ' <span class="same">TR = EN</span>' if (en and en == tr and not raw) else ""
    return (f'<tr class="{cls}" id="{anchor}"><td class="id">{rid}</td>'
            f'<td class="key">{label}{same}</td>{cell("en", en, en_eg)}{cell("tr", tr, tr_eg)}</tr>')


def _table(rows: list[str], label: str = "Key") -> str:
    if not rows:
        return '<p class="none">Nothing here.</p>'
    return (f'<table class="pairs"><thead><tr><th>Id</th><th>{label}</th><th>English</th>'
            f'<th>Turkish</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1b16;--muted:#6b665c;--line:#e2ddd2;--card:#ffffff;--accent:#8a4b12;
--ph-bg:#fff1d6;--ph-fg:#7a3d00;--note:#fff8e6;--q:#f4efe5;--code:#f0ece3}
@media (prefers-color-scheme: dark){:root{--bg:#16140f;--fg:#ece6da;--muted:#a59f92;--line:#36312a;
--card:#1e1b15;--accent:#e9a25f;--ph-bg:#3a2a12;--ph-fg:#ffc98a;--note:#2a2316;--q:#221e17;--code:#2a261f}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1280px;margin:0 auto;padding:0 16px 64px}
h1{font-size:1.6rem;margin:24px 0 4px}h2{font-size:1.3rem;margin:40px 0 8px;padding-top:8px;border-top:2px solid var(--line)}
h3{font-size:1.05rem;margin:20px 0 6px}a{color:var(--accent)}code{background:var(--code);padding:0 3px;border-radius:3px;font-size:.92em}
.note{position:sticky;top:0;z-index:5;background:var(--note);border-bottom:1px solid var(--line);padding:8px 16px;font-size:.9rem}
.note b{color:var(--accent)}[id]{scroll-margin-top:56px}
.lede{color:var(--muted);max-width:70ch}
nav.toc{columns:3 220px;font-size:.92rem;background:var(--card);border:1px solid var(--line);padding:12px 16px;border-radius:8px}
nav.toc a{display:block;break-inside:avoid;padding:1px 0}
table.pairs{width:100%;border-collapse:collapse;table-layout:fixed;background:var(--card)}
table.pairs th,table.pairs td{border:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left;overflow-wrap:anywhere}
table.pairs th{font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
table.pairs th:nth-child(1){width:4.5rem}table.pairs th:nth-child(2){width:15rem}
td.id{font-weight:600;white-space:nowrap}td.key{font-size:.85rem;color:var(--muted)}
td.en,td.tr{white-space:pre-wrap}
.ph{background:var(--ph-bg);color:var(--ph-fg);border-radius:3px;padding:0 2px;font-family:ui-monospace,Consolas,monospace;font-size:.88em}
.eg{margin-top:4px;font-size:.85rem;color:var(--muted);white-space:normal}.eg span{font-style:italic}
.same{display:inline-block;font-size:.72rem;border:1px solid var(--line);border-radius:3px;padding:0 3px}
.none{color:var(--muted);font-style:italic}
.q{background:var(--q);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:12px 0}
.q h3{margin:0 0 2px}.q .src{font-size:.8rem;color:var(--muted);margin:0 0 6px}
.q .sug{margin:8px 0 0}.q .sug b{color:var(--accent)}
.warn{border-left:4px solid var(--accent);padding:4px 10px;background:var(--card)}
table.gloss{border-collapse:collapse;background:var(--card)}table.gloss td,table.gloss th{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
@media (max-width:700px){table.pairs thead{display:none}
table.pairs,table.pairs tbody,table.pairs tr,table.pairs td{display:block;width:100%}
table.pairs tr{border:1px solid var(--line);border-radius:6px;margin:0 0 10px;padding:4px 0;background:var(--card)}
table.pairs td{border:0;padding:3px 10px}td.en::before,td.tr::before{content:attr(data-l) " ";font-weight:700;font-size:.75rem;color:var(--muted)}
nav.toc{columns:1}.note{font-size:.78rem;padding:6px 16px}[id]{scroll-margin-top:96px}}
"""


def build(site_dir: Path, out: Path, *, src_dir: Path = SITE, en: dict | None = None,
          tr: dict | None = None, questions: list | None = None) -> dict:
    """Write the pack to ``out`` and return its counts."""
    site_dir, src_dir = Path(site_dir), Path(src_dir)
    en = i18n.strings("en") if en is None else en
    tr = i18n.strings("tr") if tr is None else tr
    questions = load_questions() if questions is None else questions
    rows = collect_keys(en, tr)
    by_key = {r["key"]: r for r in rows}
    egs = examples(rows, rendered_texts(site_dir))
    stats = {"keys": len(rows), "questions": len(questions), "prose": {}, "meta": 0,
             "nav": 0, "workbook": 0, "mismatches": []}

    def key_row(r):
        return _row(f"#{r['id']}", f"k{r['id']}", f"<code>{html.escape(r['key'])}</code>",
                    r["en"], r["tr"], cls="row key", en_eg=egs.get((r["key"], "en")),
                    tr_eg=egs.get((r["key"], "tr")))

    toc, body = [], []

    # 1. Questions
    vars_path = src_dir / "_variables.yml"
    site_vars = (yaml.safe_load(vars_path.read_text(encoding="utf-8")) or {}) \
        if vars_path.is_file() else {}
    qs = []
    for n, q in enumerate(questions, 1):
        parts = [f'<div class="q" id="q{n}"><h3>Q{n}. {html.escape(q.get("title", ""))}</h3>',
                 f'<p class="src">From: {html.escape(q.get("source", ""))}</p>']
        krows = []
        for key in q.get("keys", []):
            if key not in by_key:
                raise ValueError(f"question {n}: unknown key {key}")
            r = by_key[key]
            krows.append(_row(f'<a href="#k{r["id"]}">#{r["id"]}</a>', f"q{n}-k{r['id']}",
                              f"<code>{html.escape(key)}</code>", r["en"], r["tr"], cls="row qkey"))
        if q.get("where"):
            parts.append(f'<p class="src">Where: {rich(q["where"])}</p>')
        en_text = q.get("en")
        if q.get("en_var"):
            en_text = site_vars.get(q["en_var"], "(not set)")
        if en_text is not None or q.get("tr") is not None:
            krows.append(_row("", f"q{n}-text", "text", en_text or "", q.get("tr", ""),
                              cls="row qtext"))
        parts.append(_table(krows, "Key / text"))
        parts.append(f'<p class="sug"><b>Suggestion:</b> {rich(q.get("suggest", ""))}</p></div>')
        qs.append("".join(parts))
    toc.append(f'<a href="#questions">Questions for the owner ({len(questions)})</a>')
    body.append('<section id="questions"><h2>Questions for the owner</h2>'
                '<p class="lede">Open points gathered from the task reports and reviews, merged. '
                'Answer "Q3: keep" or "Q5: option B", or give your own wording.</p>'
                + "".join(qs) + "</section>")

    # 2. Pages: title/description, prose, strings
    meta_n = prose_n = 0
    for page in PAGES:
        qmd = src_dir / page["qmd"]
        text = qmd.read_text(encoding="utf-8") if qmd.is_file() else ""
        html_rel = page["qmd"].removesuffix(".qmd") + ".html"
        links = f'<a href="{html_rel}">English page</a>'
        if page["id"] != "404":
            links += f' · <a href="tr/{html_rel}">Turkish page</a>'
        parts = [f'<section id="page-{page["id"]}"><h2>{html.escape(page["title"])}</h2>',
                 f'<p class="lede">Source <code>site/{page["qmd"]}</code> · {links}</p>']
        fm = front_matter(text)
        mrows = []
        for field in ("title", "description"):
            if field in fm or f"{field}-tr" in fm:
                meta_n += 1
                mrows.append(_row(f"M{meta_n}", f"m{meta_n}", field, fm.get(field, ""),
                                  fm.get(f"{field}-tr", "")))
        stats["meta"] += len(mrows)
        parts.append("<h3>Title and description</h3>" + _table(mrows, "Field"))
        pairs, n_en, n_tr = prose_pairs(text)
        stats["prose"][page["qmd"]] = (n_en, n_tr)
        if n_en != n_tr:
            stats["mismatches"].append(f"{page['qmd']}: en={n_en} tr={n_tr}")
            parts.append(f'<p class="warn">English has {n_en} blocks, Turkish {n_tr}.</p>')
        prows = []
        for a, b in pairs:
            prose_n += 1
            where = " · ".join(f"{x['lang']} line {x['line']}" for x in (a, b) if x)
            prows.append(_row(f"P{prose_n}", f"p{prose_n}", html.escape(where),
                              prose_text(a["src"]) if a else "", prose_text(b["src"]) if b else ""))
        parts.append(f"<h3>Prose ({len(pairs)} pairs)</h3>" + _table(prows, "Where"))
        krows = [key_row(r) for r in rows if r["group"] == page["id"]]
        parts.append(f"<h3>Strings ({len(krows)})</h3>" + _table(krows))
        toc.append(f'<a href="#page-{page["id"]}">{html.escape(page["title"])} '
                   f'({len(pairs)} prose · {len(krows)} strings)</a>')
        body.append("".join(parts) + "</section>")

    # 3. Navbar, footer, site strings
    nrows = [_row(f"N{i}", f"n{i}", f"<code>{html.escape(p)}</code>", e, t)
             for i, (p, e, t) in enumerate(profile_rows(src_dir), 1)]
    stats["nav"] = len(nrows)
    toc.append(f'<a href="#chrome">Navbar, footer and site strings ({len(nrows)})</a>')
    body.append('<section id="chrome"><h2>Navbar, footer and site strings</h2>'
                '<p class="lede"><code>site/_quarto-en.yml</code> | <code>site/_quarto-tr.yml</code>.'
                ' The explorer\'s interface strings are under Data explorer.</p>'
                + _table(nrows, "Setting") + "</section>")

    # 4. Shared strings
    for gid, title in SHARED:
        krows = [key_row(r) for r in rows if r["group"] == gid]
        if not krows:
            continue
        toc.append(f'<a href="#group-{gid}">{html.escape(title)} ({len(krows)})</a>')
        body.append(f'<section id="group-{gid}"><h2>{html.escape(title)}</h2>{_table(krows)}</section>')

    # 5. Workbooks as built
    wparts, w = [], 0
    books = workbook_rows(site_dir / "downloads")
    for book in books:
        wparts.append(f"<h3><code>{html.escape(book['en'])}</code> | "
                      f"<code>{html.escape(book['tr'])}</code></h3>")
        wrows = []
        for sheet in book["sheets"]:
            w += 1
            wrows.append(_row(f"W{w}", f"w{w}", "<b>sheet name</b>", sheet["en"], sheet["tr"]))
            for a, b in sheet["pairs"]:
                w += 1
                wrows.append(_row(f"W{w}", f"w{w}", html.escape(sheet["en"]), a, b))
            if sheet["more"]:
                wrows.append(f'<tr><td></td><td colspan="3" class="none">… {sheet["more"]} more '
                             f'distinct values in {html.escape(sheet["en"])} (same lists as the '
                             f'strings above)</td></tr>')
        wparts.append(_table(wrows, "Sheet"))
    stats["workbook"] = w
    if not books:
        wparts.append(f'<p class="none">No workbook pair in {html.escape(str(site_dir / "downloads"))}.</p>')
    toc.append(f'<a href="#workbook">Workbook as built ({w})</a>')
    body.append('<section id="workbook"><h2>Workbook as built</h2><p class="lede">Sheet names, '
                'headers, README/About and Sources text and label values, read from the rendered '
                'downloads; each distinct English | Turkish pair once.</p>'
                + "".join(wparts) + "</section>")

    # 6. Glossary
    gloss = src_dir / "i18n" / "glossary.md"
    toc.append('<a href="#glossary">Glossary (confirmed)</a>')
    body.append('<section id="glossary"><h2>Glossary</h2>'
                + (glossary_html(gloss.read_text(encoding="utf-8")) if gloss.is_file()
                   else '<p class="none">site/i18n/glossary.md not found.</p>') + "</section>")

    n_prose = stats["prose_pairs"] = prose_n
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Turkish review pack</title>
<style>{CSS}</style></head>
<body>
<div class="note"><b>How to reply:</b> cite the row id and say what to change, e.g.
"#212: change to …", "P14: second sentence → …", "Q3: keep", "W40: …". Ids: Q question ·
# string · M title/description · P prose · N navbar/footer · W workbook.</div>
<main>
<h1>Crop Markets: English | Turkish review</h1>
<p class="lede">Everything the Turkish site says, next to the English. {len(rows)} strings,
{n_prose} prose pairs, {stats['meta']} titles and descriptions, {len(questions)} questions.
<span class="ph">{{field}}</span> marks a value filled in on the page; "on page:" shows one
line as rendered. The page links open the local site (both trees under this folder).
Not linked from the site and never deployed.</p>
<nav class="toc" aria-label="Contents">{''.join(toc)}</nav>
{''.join(body)}
</main></body></html>
"""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site-dir", type=Path, default=SITE / "_site",
                        help="the rendered site (default: site/_site)")
    parser.add_argument("--out", type=Path, help=f"default: <site-dir>/{REVIEW_PAGE}")
    args = parser.parse_args(argv)
    site_dir = args.site_dir
    if not (site_dir / "index.html").is_file() or not (site_dir / "tr" / "index.html").is_file():
        print(f"{site_dir} lacks a rendered English or Turkish tree; render both languages "
              "first: python scripts/render_site.py", file=sys.stderr)
        return 2
    out = args.out or site_dir / REVIEW_PAGE
    stats = build(site_dir, out)
    print(f"wrote {out}")
    print(f"keys: {stats['keys']}")
    print(f"questions: {stats['questions']}")
    print(f"titles/descriptions: {stats['meta']}  navbar/footer rows: {stats['nav']}  "
          f"workbook rows: {stats['workbook']}")
    print(f"prose pairs: {stats['prose_pairs']}")
    for qmd, (n_en, n_tr) in stats["prose"].items():
        print(f"  {qmd}: en={n_en} tr={n_tr}")
    mismatches = stats["mismatches"] + [m for m in prose_mismatches(SITE)
                                        if m not in stats["mismatches"]]
    print("mismatches: " + ("; ".join(mismatches) if mismatches else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

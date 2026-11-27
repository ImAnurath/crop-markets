"""Excel workbook for the Downloads page: every site table, a README and the sources.

Its words (sheet names, headers, notes) come from ``site/i18n/{en,tr}.yml`` in the active
language; numbers stay numeric, so Excel shows them in the reader's own locale."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from hazelnut.site import i18n
from hazelnut.site.config import CropConfig
from hazelnut.site.crops import crop_module
from hazelnut.site.i18n import crop_country, crop_name, month_label, t
from hazelnut.site.labels import method_name

PRICE = RATIO = "0.00"


def _readable_month(ym) -> str:
    try:
        return month_label(pd.Period(ym, "M").strftime("%Y-%m"))
    except Exception:
        return str(ym) if ym else t("workbook.unknown_month")


def _bold_row(ws, row: int) -> None:
    for c in ws[row]:
        if c.value is not None:
            c.font = Font(bold=True)


def _autowidth(ws) -> None:
    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value is not None:
                widths[c.column] = max(widths.get(c.column, 0), len(str(c.value)))
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = min(max(w + 2, 8), 60)


def _placeholder(ws) -> None:
    text = t("workbook.not_available")
    ws["A1"] = text
    ws.column_dimensions["A"].width = len(text) + 2


def _write_table(ws, df: pd.DataFrame, spec: dict, start: int = 1,
                 values: dict | None = None) -> int:
    """Write df with readable headers from row ``start``; return the next free row.
    ``values`` maps a column to a function giving each text value's label."""
    values = values or {}
    cols = [c for c in spec if c in df.columns]
    for j, c in enumerate(cols, 1):
        ws.cell(start, j, spec[c][0])
    _bold_row(ws, start)
    for i, rec in enumerate(df[cols].itertuples(index=False), start + 1):
        for j, (c, v) in enumerate(zip(cols, rec), 1):
            if pd.isna(v):
                continue
            if c in values and isinstance(v, str):
                v = values[c](v)
            cell = ws.cell(i, j, v.item() if hasattr(v, "item") else v)
            if spec[c][1]:
                cell.number_format = spec[c][1]
    return start + len(df) + 1


def _read(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path) if path.exists() else None
    except Exception:
        return None


def _scoreboard(ws, data_dir: Path) -> bool:
    formats = {"method": None, "horizon": "0", "n": "0", "mae": PRICE, "ratio": RATIO}
    spec = {c: (t(f"workbook.column.{c}"), fmt) for c, fmt in formats.items()}
    dev = _read(data_dir / "results" / "scoreboard_dev.csv")
    if dev is None:
        _placeholder(ws)
        return False
    holdout = _read(data_dir / "results" / "scoreboard_holdout.csv")

    def named(df):
        return df.assign(method=df["method"].map(lambda m: method_name(str(m))))

    nxt = _write_table(ws, named(dev), spec)
    ws.cell(nxt, 1, t("workbook.ratio_note"))
    if holdout is not None:
        ws.cell(nxt + 2, 1, t("workbook.holdout_label")).font = Font(bold=True)
        _write_table(ws, named(holdout), spec, start=nxt + 3)
    ws.freeze_panes = "A2"
    return True


def _sheet_name(key: str) -> str:
    """The name of a sheet every workbook has: "readme", "scoreboard" or "sources"."""
    return t(f"workbook.sheet.{key}")


def generic_notes() -> dict[str, str]:
    """The notes of the sheets every crop's workbook ends with (scoreboard, sources)."""
    return {_sheet_name(k): t(f"workbook.note.{k}") for k in ("scoreboard", "sources")}


def workbook_filename(slug: str, lang: str | None = None) -> str:
    """The workbook's file name under ``site/downloads/`` in ``lang`` (default: the active
    language): ``<slug>-market-data.xlsx`` in English, ``<slug>-market-data-<lang>.xlsx``
    in another language."""
    lang = lang or i18n.LANG
    return f"{slug}-market-data.xlsx" if lang == i18n.DEFAULT else f"{slug}-market-data-{lang}.xlsx"


def sheet_notes(slug: str) -> dict[str, str]:
    """Each data sheet's one-line note, in workbook order (after the README)."""
    return {**crop_module(slug).WORKBOOK_SHEET_NOTES, **generic_notes()}


def sheet_list(slug: str) -> list[tuple[str, str]]:
    """(sheet name, note) for every sheet of the crop's workbook, in workbook order."""
    return [(_sheet_name("readme"), t("workbook.note.readme")), *sheet_notes(slug).items()]


def _readme(ws, crop, site_url, manifest, sheet_ok, notes, output_sheets) -> None:
    ws["A1"] = t("workbook.title", crop=crop_name(crop), country=crop_country(crop))
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = t("workbook.as_of", month=_readable_month(manifest.get("as_of")))
    ws["A3"] = site_url
    row = 5
    ws.cell(row, 1, t("workbook.sheet_header")).font = Font(bold=True)
    ws.cell(row, 2, t("workbook.contents_header")).font = Font(bold=True)
    for name, note in notes.items():
        row += 1
        ws.cell(row, 1, name)
        ws.cell(row, 2, note if sheet_ok.get(name, True) else t("workbook.note_unavailable", note=note))
    outputs = manifest.get("outputs", {})
    stale = [(n, o) for n, o in outputs.items() if isinstance(o, dict) and o.get("stale")]
    if stale:
        row += 2
        ws.cell(row, 1, t("workbook.stale_title")).font = Font(bold=True)
        for n, o in stale:
            row += 1
            as_of = _readable_month(o["as_of"]) if o.get("as_of") else t("workbook.no_data")
            ws.cell(row, 1, output_sheets.get(n, n))
            ws.cell(row, 2, t("workbook.stale_as_of", month=as_of))
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 80


def _sources(ws, sources) -> None:
    ws.append([t("sources.provider"), t("sources.what"), t("workbook.sources_url"),
               t("sources.terms")])
    _bold_row(ws, 1)
    for s in sources:
        ws.append(list(s))
    ws.freeze_panes = "A2"
    _autowidth(ws)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top")


def build_workbook(data_dir: Path, out_path: Path, crop: CropConfig,
                   site_url: str | None = None) -> Path:
    """Write the crop's workbook in the active language; ``site_url`` (default: the active
    language's site root) goes on the README sheet."""
    site_url = site_url or i18n.site_url()
    data_dir, out_path = Path(data_dir), Path(out_path)
    try:
        manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            manifest = {}
    except Exception:
        manifest = {}

    mod = crop_module(crop.slug)
    sheets, sources = mod.WORKBOOK_SHEETS, mod.WORKBOOK_SOURCES
    notes = sheet_notes(crop.slug)
    output_sheets = {csv.removesuffix(".csv"): name for name, (csv, _) in sheets.items()}

    wb = Workbook()
    readme = wb.active
    readme.title = _sheet_name("readme")
    sheet_ok: dict[str, bool] = {}
    for sheet, (csv, spec) in sheets.items():
        ws = wb.create_sheet(sheet)
        df = _read(data_dir / csv)
        sheet_ok[sheet] = df is not None
        if df is None:
            _placeholder(ws)
            continue
        _write_table(ws, df, spec, values=getattr(mod, "WORKBOOK_VALUES", {}))
        ws.freeze_panes = "A2"
        _autowidth(ws)
    ws = wb.create_sheet(_sheet_name("scoreboard"))
    sheet_ok[ws.title] = _scoreboard(ws, data_dir)
    _autowidth(ws)
    _sources(wb.create_sheet(_sheet_name("sources")), sources)
    _readme(readme, crop, site_url, manifest, sheet_ok, notes, output_sheets)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path

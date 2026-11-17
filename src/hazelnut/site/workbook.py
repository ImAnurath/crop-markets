"""Excel workbook for the Downloads page: every site table, a README and the sources."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from hazelnut.site.config import SITE_URL, CropConfig

NOT_AVAILABLE = "Not available in this refresh."
HOLDOUT_LABEL = "Holdout, scored once, never tuned on"
RATIO_NOTE = "Ratio to naive = MAE / naive MAE; below 1 beats naive."

PRICE, KG, SHARE, TONNES, RATIO = "0.00", "#,##0", "0.0%", "#,##0", "0.00"

METHOD_NAMES = {
    "naive": "Naive", "seasonal_naive": "Seasonal naive", "sarima": "SARIMA",
    "sarimax": "SARIMAX", "season_reg": "Season regression", "lightgbm": "LightGBM",
    "chronos": "Chronos-Bolt",
}

# sheet -> (csv name, {column: (header, number format or None)})
SHEETS = {
    "Prices": ("prices_monthly.csv", {
        "month": ("Month", None), "season": ("Season", None), "usd_kg": ("USD/kg", PRICE),
        "try_kg": ("TL/kg", PRICE), "usd_try": ("TL per USD", "0.0000")}),
    "Ordu": ("ordu_monthly.csv", {
        "month": ("Month", None), "season": ("Season", None), "try_kg": ("TL/kg", PRICE),
        "usd_kg": ("USD/kg", PRICE), "trade_days": ("Trading days", "0")}),
    "Exports": ("exports_monthly.csv", {
        "month": ("Month", None), "product": ("Product", None), "partner": ("Destination", None),
        "net_kg": ("Net weight (kg)", KG), "fob_usd": ("FOB value (USD)", KG)}),
    "Top destinations": ("exports_top.csv", {
        "partner": ("Destination", None), "net_kg": ("Net weight (kg)", KG),
        "fob_usd": ("FOB value (USD)", KG), "share": ("Share of exports", SHARE)}),
    "Crop": ("crop_by_year.csv", {
        "year": ("Year", "0"), "season": ("Season", None),
        "giresun_estimate_t": ("Giresun estimate (t)", TONNES),
        "giresun_registered_t": ("Giresun registered (t)", TONNES),
        "national_estimate_t": ("National estimate (t)", TONNES),
        "season_avg_usd": ("Season average (USD/kg)", PRICE)}),
    "Forecast range": ("price_range.csv", {
        "horizon": ("Horizon (months)", "0"), "target_month": ("Target month", None),
        "q05": ("5th percentile (USD/kg)", PRICE), "q10": ("10th percentile (USD/kg)", PRICE),
        "q50": ("Median (USD/kg)", PRICE), "q90": ("90th percentile (USD/kg)", PRICE),
        "q95": ("95th percentile (USD/kg)", PRICE), "from_month": ("Forecast from month", None),
        "from_usd": ("Price at forecast origin (USD/kg)", PRICE)}),
}

SHEET_NOTES = {
    "Prices": "Monthly Giresun price, USD/kg and TL/kg",
    "Ordu": "Monthly Ordu exchange price",
    "Exports": "Monthly exports by destination",
    "Top destinations": "Largest export destinations",
    "Crop": "Crop size by year and season average price",
    "Forecast range": "Empirical price range by horizon, in USD/kg",
    "Scoreboard": "Backtest accuracy by method; holdout table scored once, never tuned on",
    "Sources": "Data providers, what we use and credit",
}

SOURCES = [
    ("UN Comtrade", "Monthly export volumes and values by destination (HS 080221, 080222)",
     "https://comtradeplus.un.org/", "Credit the source; see provider terms"),
    ("FAOSTAT", "Annual national production statistics",
     "https://www.fao.org/faostat/", "CC BY 4.0"),
    ("TOBB", "Commodity exchange price records (TOBB exchange price query)",
     "https://borsa.tobb.org.tr/", "Credit the source; see provider terms"),
    ("Giresun Commodity Exchange", "Monthly prices, crop estimates and trade volumes",
     "https://www.giresuntb.org.tr/", "Credit the source; see provider terms"),
    ("Ordu Commodity Exchange", "Daily prices, published by the exchange as a public Google Sheet",
     "https://docs.google.com/spreadsheets/d/1aeIzaRkKD4XvKZMRu5A4ZJywzNNUn6Ww/htmlview",
     "Credit the source; see provider terms"),
    ("Open-Meteo", "Historical daily weather (frost days)",
     "https://open-meteo.com/", "CC BY 4.0"),
    ("ECB", "Daily euro foreign-exchange reference rates",
     "https://data.ecb.europa.eu/", "Free reuse with the source acknowledged"),
    ("OECD", "Consumer price index",
     "https://data-explorer.oecd.org/", "CC BY 4.0"),
]


def _readable_month(ym) -> str:
    try:
        return pd.Period(ym, "M").strftime("%B %Y")
    except Exception:
        return str(ym) if ym else "unknown"


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
    ws["A1"] = NOT_AVAILABLE
    ws.column_dimensions["A"].width = len(NOT_AVAILABLE) + 2


def _write_table(ws, df: pd.DataFrame, spec: dict, start: int = 1) -> int:
    """Write df with readable headers from row ``start``; return the next free row."""
    cols = [c for c in spec if c in df.columns]
    for j, c in enumerate(cols, 1):
        ws.cell(start, j, spec[c][0])
    _bold_row(ws, start)
    for i, rec in enumerate(df[cols].itertuples(index=False), start + 1):
        for j, (c, v) in enumerate(zip(cols, rec), 1):
            if pd.isna(v):
                continue
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
    spec = {"method": ("Method", None), "horizon": ("Horizon (months)", "0"),
            "n": ("Forecasts scored", "0"), "mae": ("MAE (USD/kg)", PRICE),
            "ratio": ("Ratio to naive", RATIO)}
    dev = _read(data_dir / "results" / "scoreboard_dev.csv")
    if dev is None:
        _placeholder(ws)
        return False
    holdout = _read(data_dir / "results" / "scoreboard_holdout.csv")

    def named(df):
        return df.assign(method=df["method"].map(lambda m: METHOD_NAMES.get(m, m)))

    nxt = _write_table(ws, named(dev), spec)
    ws.cell(nxt, 1, RATIO_NOTE)
    if holdout is not None:
        ws.cell(nxt + 2, 1, HOLDOUT_LABEL).font = Font(bold=True)
        _write_table(ws, named(holdout), spec, start=nxt + 3)
    ws.freeze_panes = "A2"
    return True


def _readme(ws, crop, site_url, manifest, sheet_ok) -> None:
    ws["A1"] = f"{crop.name} market data ({crop.country})"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Data as of {_readable_month(manifest.get('as_of'))}"
    ws["A3"] = site_url
    row = 5
    ws.cell(row, 1, "Sheet").font = Font(bold=True)
    ws.cell(row, 2, "Contents").font = Font(bold=True)
    for name, note in SHEET_NOTES.items():
        row += 1
        ws.cell(row, 1, name)
        ws.cell(row, 2, note if sheet_ok.get(name, True) else f"{note} (not available in this refresh)")
    outputs = manifest.get("outputs", {})
    stale = [(n, o) for n, o in outputs.items() if isinstance(o, dict) and o.get("stale")]
    if stale:
        row += 2
        ws.cell(row, 1, "Stale outputs (kept from an earlier refresh)").font = Font(bold=True)
        for n, o in stale:
            row += 1
            as_of = _readable_month(o["as_of"]) if o.get("as_of") else "no data"
            ws.cell(row, 1, n)
            ws.cell(row, 2, f"stale, as of {as_of}")
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 80


def _sources(ws) -> None:
    ws.append(["Provider", "What we use", "URL", "Credit and terms"])
    _bold_row(ws, 1)
    for s in SOURCES:
        ws.append(list(s))
    ws.freeze_panes = "A2"
    _autowidth(ws)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top")


def build_workbook(data_dir: Path, out_path: Path, crop: CropConfig, site_url: str = SITE_URL) -> Path:
    data_dir, out_path = Path(data_dir), Path(out_path)
    try:
        manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            manifest = {}
    except Exception:
        manifest = {}

    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    sheet_ok: dict[str, bool] = {}
    for sheet, (csv, spec) in SHEETS.items():
        ws = wb.create_sheet(sheet)
        df = _read(data_dir / csv)
        sheet_ok[sheet] = df is not None
        if df is None:
            _placeholder(ws)
            continue
        _write_table(ws, df, spec)
        ws.freeze_panes = "A2"
        _autowidth(ws)
    ws = wb.create_sheet("Scoreboard")
    sheet_ok["Scoreboard"] = _scoreboard(ws, data_dir)
    _autowidth(ws)
    _sources(wb.create_sheet("Sources"))
    _readme(readme, crop, site_url, manifest, sheet_ok)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path

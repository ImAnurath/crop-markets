"""Turn the latest raw snapshot of each source into tidy CSV tables in data/interim/.

One table per dataset, long format, plain column names. Light parsing only: numbers are
converted, dates normalised, and pre-2005 lira values are flagged (not converted) so the
exploration can decide how to handle them.

Usage:
    python scripts/build_tables.py
"""

import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "interim"

TR_MONTHS = {
    "OCAK": 1, "ŞUBAT": 2, "MART": 3, "NİSAN": 4, "MAYIS": 5, "HAZİRAN": 6,
    "TEMMUZ": 7, "AĞUSTOS": 8, "EYLÜL": 9, "EKİM": 10, "KASIM": 11, "ARALIK": 12,
}


def latest(source: str) -> Path:
    """Most recent dated snapshot folder for a source."""
    return sorted(p for p in (RAW / source).iterdir() if p.is_dir())[-1]


def tr_number(text: str) -> float | None:
    """Turkish number format: '.' groups thousands, ',' marks decimals. '1.234,56' -> 1234.56"""
    text = text.strip().rstrip("*").strip()
    if not re.search(r"\d", text):
        return None
    return float(text.replace(".", "").replace(",", "."))


def save(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"{name}: {len(df):,} rows")


# --- Prices ---------------------------------------------------------------------------

def ordu_daily() -> None:
    """Ordu sheet: a day x month grid per year -> one row per trading day."""
    rows = []
    for path in sorted(latest("ordu_sheet").glob("*.csv")):
        year = int(path.stem)
        grid = list(csv.reader(path.open(encoding="utf-8")))
        months = [TR_MONTHS[m.strip()] for m in grid[2][1:13]]
        for line in grid[3:34]:
            if not line or not line[0].strip().isdigit():
                continue
            day = int(line[0])
            for month, cell in zip(months, line[1:13]):
                value = tr_number(cell)
                if value is None:
                    continue
                rows.append({
                    "date": f"{year}-{month:02d}-{day:02d}",
                    "price": value,
                    "special_terms": cell.strip().endswith("*"),
                    "old_lira": year < 2005,
                })
    save(pd.DataFrame(rows).sort_values("date"), "ordu_daily")


def tobb_daily() -> None:
    """TOBB form results: one HTML file per grade and exchange -> one row per trading day."""
    rows = []
    for path in sorted(latest("tobb").glob("*.html")):
        grade, exchange = path.stem.split("__")
        html = path.read_text(encoding="utf-8")
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
            if len(cells) < 8 or not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", cells[1]):
                continue
            d, m, y = cells[1].split(".")
            rows.append({
                "date": f"{y}-{m}-{d}", "exchange": exchange, "grade": grade,
                "price_min": tr_number(cells[2]), "price_max": tr_number(cells[3]),
                "price_avg": tr_number(cells[4]), "quantity_kg": tr_number(cells[5]),
                "trades": tr_number(cells[6]), "value_try": tr_number(cells[7]),
            })
    save(pd.DataFrame(rows).sort_values(["grade", "exchange", "date"]), "tobb_daily")


def giresun_props() -> dict:
    """The page is a Next.js app; its data travels as JSON inside self.__next_f.push(...) calls."""
    html = (latest("giresun") / "gtb-verileri.html").read_text(encoding="utf-8")
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
    payload = "".join(json.loads(f'"{c}"') for c in chunks)
    start = payload.find('["$","$L13",null,')
    element, _ = json.JSONDecoder().raw_decode(payload[start:])
    return element[3]


def giresun_tables() -> None:
    props = giresun_props()
    # Spelled out because Python's .capitalize() mangles the Turkish dotted İ.
    month_names = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
                   "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}

    # Monthly price statistics, 1985 onward. TL values before 2005 are old lira.
    rows = []
    for block in props["fiyat"]:
        for r in block["rows"]:
            rows.append({
                "year": r["year"], "month": month_names[r["month"]], "usd_try": r["kur"],
                "price_min_try": r["enAzTl"], "price_max_try": r["enCokTl"], "price_avg_try": r["ortTl"],
                "price_min_usd": r["enAzUsd"], "price_max_usd": r["enCokUsd"], "price_avg_usd": r["ortUsd"],
                "old_lira": r["year"] < 2005,
            })
    save(pd.DataFrame(rows).drop_duplicates(["year", "month"]).sort_values(["year", "month"]),
         "giresun_monthly_price")

    # Registered volume by month and buyer type, per season. A season starts in August of
    # the harvest year and runs to the next August; that closing August is labelled
    # "Ağustos_S". Months Jan-Jul and "Ağustos_S" fall in calendar year season + 1.
    rows = []
    for block in props["kurum"]:
        for r in block["rows"]:
            if r["total"]:
                continue
            label = r["label"]
            closing = label.endswith("_S")
            month = month_names[label.removesuffix("_S")]
            year = block["season"] + (1 if closing or month < 8 else 0)
            for buyer in ["tuccar", "kooperatif", "tmo"]:
                b = r[buyer]
                rows.append({
                    "season": block["season"], "year": year, "month": month,
                    "buyer": {"tuccar": "trader", "kooperatif": "cooperative", "tmo": "tmo"}[buyer],
                    "quantity_kg": b["miktar"], "value_try": b["tutar"], "price_try": b["fiyat"],
                })
    save(pd.DataFrame(rows), "giresun_monthly_volume")

    # Crop estimate vs registered actual, per year.
    save(pd.DataFrame(props["gerceklesme"]).rename(columns={
        "tahmin": "estimate_t", "gerceklesen": "registered_t", "oran": "ratio_pct"}),
        "giresun_crop")

    # Daily volume-weighted price, current season only.
    daily = pd.DataFrame(props["daily"]["points"]).assign(season=props["daily"]["season"])
    save(daily.rename(columns={"price": "price_try", "quantity": "quantity_kg"}), "giresun_daily")


# --- Drivers --------------------------------------------------------------------------

def comtrade_monthly() -> None:
    folder = latest("comtrade")
    partners = {p["PartnerCode"]: p["PartnerDesc"]
                for p in json.loads((folder / "partner_areas.json").read_text(encoding="utf-8"))["results"]}
    rows = []
    for path in sorted(folder.glob("[0-9]*.json")):
        for r in json.loads(path.read_text(encoding="utf-8")).get("data", []):
            rows.append({
                "month": f"{r['period'][:4]}-{r['period'][4:]}",
                "hs_code": r["cmdCode"],
                "product": {"080221": "in_shell", "080222": "shelled"}.get(r["cmdCode"], r["cmdCode"]),
                "partner": partners.get(r["partnerCode"], str(r["partnerCode"])),
                "net_kg": r["netWgt"], "fob_usd": r["primaryValue"],
            })
    save(pd.DataFrame(rows).sort_values(["month", "hs_code", "partner"]), "comtrade_monthly")


def faostat_tables() -> None:
    folder = latest("faostat")

    def read_hazelnut(zip_name: str) -> pd.DataFrame:
        with zipfile.ZipFile(folder / zip_name) as z:
            name = next(n for n in z.namelist() if n.endswith("(Normalized).csv"))
            with z.open(name) as f:
                chunks = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"), chunksize=500_000,
                                     dtype={"Note": str})
                return pd.concat(c[c["Item"].str.startswith("Hazelnuts")] for c in chunks)

    prod = read_hazelnut("Production_Crops_Livestock_E_All_Data_(Normalized).zip")
    save(prod[["Area", "Element", "Year", "Unit", "Value", "Flag"]]
         .rename(columns=str.lower), "faostat_production")

    prices = read_hazelnut("Prices_E_All_Data_(Normalized).zip")
    keep = [c for c in ["Area", "Element", "Year", "Months", "Unit", "Value", "Flag"] if c in prices]
    save(prices[keep].rename(columns=str.lower), "faostat_prices")


def weather_daily() -> None:
    frames = []
    for path in sorted(latest("open_meteo").glob("*.json")):
        daily = json.loads(path.read_text(encoding="utf-8"))["daily"]
        frames.append(pd.DataFrame(daily).rename(columns={"time": "date"}).assign(location=path.stem))
    save(pd.concat(frames), "weather_daily")


def fx_daily() -> None:
    folder = latest("ecb_fx")
    series = {}
    for cur in ["TRY", "USD"]:
        df = pd.read_csv(folder / f"EUR_{cur}.csv", usecols=["TIME_PERIOD", "OBS_VALUE"])
        series[cur] = df.set_index("TIME_PERIOD")["OBS_VALUE"]
    fx = pd.DataFrame(series).dropna()
    fx["usd_try"] = fx["TRY"] / fx["USD"]
    fx = fx.rename(columns={"TRY": "eur_try", "USD": "eur_usd"}).rename_axis("date").reset_index()
    save(fx, "fx_daily")


def cpi_monthly() -> None:
    df = pd.read_csv(latest("oecd_cpi") / "turkey_cpi_monthly.csv", usecols=["TIME_PERIOD", "OBS_VALUE"])
    save(df.rename(columns={"TIME_PERIOD": "month", "OBS_VALUE": "cpi"}).sort_values("month"), "cpi_monthly")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252
    OUT.mkdir(parents=True, exist_ok=True)
    for step in [ordu_daily, tobb_daily, giresun_tables, comtrade_monthly,
                 faostat_tables, weather_daily, fx_daily, cpi_monthly]:
        try:
            step()
        except Exception as exc:
            print(f"{step.__name__}: FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()

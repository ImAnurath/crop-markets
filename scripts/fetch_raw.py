"""Download raw data from every source in docs/data-sources.md.

Each source is saved untouched under data/raw/<source>/<YYYY-MM-DD>/, so every run keeps
its own snapshot. Nothing here parses or cleans; that happens later.

Usage:
    python scripts/fetch_raw.py              # all sources
    python scripts/fetch_raw.py ordu tobb    # only some
"""

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import certifi
import requests

ROOT = Path(__file__).resolve().parent.parent
TODAY = dt.date.today()
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "hazelnut-market-data/0.1 (research project)"


def out_dir(source: str) -> Path:
    path = ROOT / "data" / "raw" / source / TODAY.isoformat()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get(url: str, **kwargs) -> requests.Response:
    resp = SESSION.get(url, timeout=kwargs.pop("timeout", 60), **kwargs)
    resp.raise_for_status()
    return resp


# --- Prices ---------------------------------------------------------------------------

ORDU_SHEET_ID = "1aeIzaRkKD4XvKZMRu5A4ZJywzNNUn6Ww"


def fetch_ordu() -> None:
    """Ordu exchange daily prices: one Google Sheet tab per year, each saved as CSV."""
    out = out_dir("ordu_sheet")
    html = get(f"https://docs.google.com/spreadsheets/d/{ORDU_SHEET_ID}/htmlview").text
    # The tab list sits in a script block: {name: "2024", pageUrl: "...gid=1052288668", ...}
    tabs = re.findall(r'name: "([^"]+)"[^}]*?gid=(\d+)', html)
    for name, gid in tabs:
        url = f"https://docs.google.com/spreadsheets/d/{ORDU_SHEET_ID}/export?format=csv&gid={gid}"
        (out / f"{name.strip()}.csv").write_bytes(get(url).content)
    print(f"ordu: {len(tabs)} tabs")


TOBB_GRADES = {
    204: "kernel_11-13", 205: "kernel_12-14", 206: "kernel_13-15", 908: "kernel_9-11",
    906: "kernel_9-15_class1", 907: "kernel_9-15_class2", 905: "kernel_9-15_extra",
    909: "kernel_wrinkled", 910: "kernel_defective", 202: "inshell_sivri",
    911: "inshell_tombul_giresun", 904: "inshell_tombul_levant",
}
TOBB_EXCHANGES = {
    "5DÜ10": "duzce", "5FA10": "fatsa", "5GI10": "giresun",
    "5OR10": "ordu", "5AD20": "sakarya", "5TR10": "trabzon",
}


def tobb_ca_bundle() -> str:
    """CA bundle that also trusts the intermediate certificate TOBB's server forgets to send.

    Browsers fetch the missing intermediate on their own; Python does not, so plain
    requests fail with "unable to verify the first certificate". certs/sectigo_dv_r36.pem
    is that public intermediate, downloaded from Sectigo. Verification stays fully on.
    """
    bundle = ROOT / "data" / "raw" / ".tobb_ca_bundle.pem"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        Path(certifi.where()).read_text(encoding="utf-8")
        + (ROOT / "certs" / "sectigo_dv_r36.pem").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return str(bundle)


def fetch_tobb() -> None:
    """TOBB exchange prices: one form query per grade and exchange, saved as returned HTML."""
    out = out_dir("tobb")
    ca = tobb_ca_bundle()
    saved = 0
    for code, grade in TOBB_GRADES.items():
        for exch_code, exch in TOBB_EXCHANGES.items():
            form = {
                "gun1": "01", "ay1": "01", "yil1": "2000",
                "gun2": f"{TODAY.day:02d}", "ay2": f"{TODAY.month:02d}", "yil2": str(TODAY.year),
                "borsa": exch_code, "siralama1": "tarih", "siralama2": "borsa_adi",
                "gonder": "Sorgula",
            }
            resp = SESSION.post(
                f"https://borsa.tobb.org.tr/fiyat_sorgu2.php?ana_kod=9&alt_kod={code}",
                data=form, verify=ca, timeout=120,
            )
            resp.raise_for_status()
            if re.search(r"<td[^>]*>\s*\d{2}\.\d{2}\.\d{4}\s*</td>", resp.text):
                (out / f"{grade}__{exch}.html").write_text(resp.text, encoding="utf-8")
                saved += 1
            time.sleep(0.5)
    print(f"tobb: {saved} grade/exchange combinations with data")


def fetch_giresun() -> None:
    """Giresun exchange statistics page; the data is JSON embedded in the HTML."""
    out = out_dir("giresun")
    html = get("https://www.giresuntb.org.tr/istatistikler/gtb-verileri").text
    (out / "gtb-verileri.html").write_text(html, encoding="utf-8")
    print("giresun: page saved")


# --- Drivers --------------------------------------------------------------------------

def fetch_comtrade(start: str = "2000-01") -> None:
    """Turkey's monthly hazelnut exports by partner (HS 080221 in-shell, 080222 shelled).

    The free preview API allows one month per call and limits call rate, so this takes
    roughly ten minutes. Months already saved today are skipped, so a rerun resumes.
    """
    out = out_dir("comtrade")
    ref = out / "partner_areas.json"
    if not ref.exists():
        ref.write_bytes(get("https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json").content)

    year, month = map(int, start.split("-"))
    empty_streak = 0
    while (year, month) <= (TODAY.year, TODAY.month):
        period = f"{year}{month:02d}"
        target = out / f"{period}.json"
        if not target.exists():
            url = (
                "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
                f"?reporterCode=792&period={period}&cmdCode=080221,080222&flowCode=X"
            )
            for attempt in range(5):
                resp = SESSION.get(url, timeout=60)
                if resp.status_code == 429:  # rate limited, back off and retry
                    time.sleep(3 * (attempt + 1))
                    continue
                resp.raise_for_status()
                break
            resp.raise_for_status()  # still rate limited after every retry: fail the source
            payload = resp.json()
            if payload.get("count", 0) >= 500:
                print(f"  warning: {period} hit the 500-row cap, data may be truncated")
            target.write_text(json.dumps(payload), encoding="utf-8")
            time.sleep(1.2)
            empty_streak = empty_streak + 1 if not payload.get("count") else 0
        month += 1
        if month == 13:
            year, month = year + 1, 1
    print(f"comtrade: done, last {empty_streak} months empty (normal reporting lag)")


def fetch_faostat() -> None:
    """FAOSTAT bulk files: crop production (all countries) and producer prices."""
    out = out_dir("faostat")
    base = "https://bulks-faostat.fao.org/production/"
    for name in ["Production_Crops_Livestock_E_All_Data_(Normalized).zip",
                 "Prices_E_All_Data_(Normalized).zip"]:
        (out / name).write_bytes(get(base + name, timeout=300).content)
    print("faostat: 2 zip files")


# Main hazelnut provinces. City-level points; good enough to start exploring.
WEATHER_POINTS = {
    "ordu": (40.98, 37.88), "giresun": (40.91, 38.39), "trabzon": (41.00, 39.72),
    "samsun_carsamba": (41.20, 36.72), "duzce": (40.84, 31.16), "sakarya": (40.78, 30.40),
}
WEATHER_VARS = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "precipitation_sum", "snowfall_sum",
]


def fetch_weather(start: str = "1980-01-01") -> None:
    """Open-Meteo daily history for each hazelnut province.

    The free tier counts a long date range as many calls (roughly one per two weeks of
    data per handful of variables), so one 45-year request is heavy. We start in 1980,
    wait between locations, and skip files already saved today so a rerun resumes.
    """
    out = out_dir("open_meteo")
    end = TODAY - dt.timedelta(days=7)  # the archive lags a few days
    for name, (lat, lon) in WEATHER_POINTS.items():
        target = out / f"{name}.json"
        if target.exists():
            continue
        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
            f"&daily={','.join(WEATHER_VARS)}&timezone=Europe%2FIstanbul"
        )
        for attempt in range(4):
            resp = SESSION.get(url, timeout=300)
            if resp.status_code == 429:  # per-minute limit; wait it out
                time.sleep(70)
                continue
            resp.raise_for_status()
            break
        resp.raise_for_status()
        target.write_bytes(resp.content)
        time.sleep(70)
    print(f"weather: {len(WEATHER_POINTS)} locations")


def fetch_fx() -> None:
    """ECB daily reference rates for TRY and USD (both per euro). USD/TRY = TRY / USD."""
    out = out_dir("ecb_fx")
    for cur in ["TRY", "USD"]:
        url = f"https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A?format=csvdata"
        (out / f"EUR_{cur}.csv").write_bytes(get(url, timeout=120).content)
    print("fx: 2 series")


def fetch_cpi() -> None:
    """Turkish monthly consumer price index from the OECD."""
    out = out_dir("oecd_cpi")
    url = (
        "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/"
        "TUR.M.N.CPI.IX._T.N._Z?format=csvfilewithlabels"
    )
    (out / "turkey_cpi_monthly.csv").write_bytes(get(url, timeout=120).content)
    print("cpi: saved")


SOURCES = {
    "ordu": fetch_ordu, "tobb": fetch_tobb, "giresun": fetch_giresun,
    "comtrade": fetch_comtrade, "faostat": fetch_faostat, "weather": fetch_weather,
    "fx": fetch_fx, "cpi": fetch_cpi,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", help=f"any of: {', '.join(SOURCES)} (default: all)")
    names = parser.parse_args().sources or list(SOURCES)
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        parser.error(f"unknown source(s): {', '.join(unknown)}")
    failed = []
    for name in names:
        try:
            SOURCES[name]()
        except Exception as exc:  # keep going so one broken source doesn't block the rest
            print(f"{name}: FAILED: {type(exc).__name__}: {exc}")
            failed.append(name)
    if failed:
        print("failed sources:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

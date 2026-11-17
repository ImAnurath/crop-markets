"""Site data writer: builds the site tables, the price range and the stat strip, with fallback.

Each output is built fresh when its source tables are present and its builder succeeds.
Otherwise the last good file in ``out_dir`` is kept and marked ``stale`` in the manifest.
If a core output cannot be built fresh, ``SiteDataError`` is raised before any file is touched.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from hazelnut.forecast.dataset import _FILES, MANUAL_DIR, NATIONAL_CROP_FILE
from hazelnut.forecast.dataset import DATA_DIR as INTERIM_DIR
from hazelnut.forecast.intervals import LEVELS, column
from hazelnut.forecast.methods.baselines import EmpiricalNaive
from hazelnut.site.config import CropConfig
from hazelnut.site.hazelnut_data import BUILDERS

CORE_OUTPUTS = ("prices_monthly", "price_range", "stats")
ORDU_FILE = "ordu_daily.csv"
HORIZONS = (1, 3, 6)


class SiteDataError(Exception):
    pass


def load_interim_tables(
    interim_dir: Path = INTERIM_DIR, manual_dir: Path = MANUAL_DIR
) -> dict[str, pd.DataFrame]:
    """Read every interim/manual table that exists and parses; never raises."""
    files = {key: Path(interim_dir) / name for key, name in _FILES.items()}
    files["ordu_daily"] = Path(interim_dir) / ORDU_FILE
    files["national_crop"] = Path(manual_dir) / NATIONAL_CROP_FILE
    tables: dict[str, pd.DataFrame] = {}
    for key, path in files.items():
        try:
            if path.exists():
                tables[key] = pd.read_csv(path)
        except Exception:
            continue
    return tables


def _both(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.dropna(subset=["usd_kg", "try_kg"]).sort_values("month")


def price_range(prices: pd.DataFrame, horizons=HORIZONS) -> pd.DataFrame:
    """USD/kg quantiles (empirical naive) from the last month with both USD and TRY prices."""
    both = _both(prices)
    if both.empty:
        raise ValueError("no month with both USD and TRY prices")
    last = pd.Period(both["month"].iloc[-1], "M")
    usd = prices.dropna(subset=["usd_kg"])
    hist = pd.Series(
        usd["usd_kg"].to_numpy(dtype=float), index=pd.PeriodIndex(usd["month"], freq="M")
    ).sort_index()
    hist = hist[hist.index <= last]
    q = EmpiricalNaive().quantiles(hist, pd.DataFrame(index=hist.index), list(horizons), LEVELS)
    cols = [column(lv) for lv in LEVELS]
    rows = []
    for h in horizons:
        vals = q.get(h)
        if vals is None:
            continue
        rows.append(
            {
                "horizon": h,
                "target_month": str(last + h),
                **dict(zip(cols, np.sort(np.asarray(vals, dtype=float)))),
                "from_month": str(last),
                "from_usd": float(hist.iloc[-1]),
            }
        )
    if not rows:
        raise ValueError("not enough history for a price range")
    return pd.DataFrame(rows)[["horizon", "target_month", *cols, "from_month", "from_usd"]]


def _mom(series: pd.Series, month: pd.Period) -> float | None:
    prev = month - 1
    if prev not in series.index or not np.isfinite(series[prev]) or series[prev] <= 0:
        return None
    return float(series[month] / series[prev] - 1)


def stat_strip(prices: pd.DataFrame, crop: pd.DataFrame | None) -> dict:
    both = _both(prices)
    if both.empty:
        raise ValueError("no month with both USD and TRY prices")
    month = pd.Period(both["month"].iloc[-1], "M")
    idx = pd.PeriodIndex(prices["month"], freq="M")
    usd = pd.Series(prices["usd_kg"].to_numpy(dtype=float), index=idx)
    tr = pd.Series(prices["try_kg"].to_numpy(dtype=float), index=idx)
    usd_now = float(usd[month])
    peak_month = usd[usd.index <= month].idxmax()
    peak = float(usd[peak_month])
    stats = {
        "as_of": str(month),
        "usd_kg": usd_now,
        "usd_mom": _mom(usd, month),
        "try_kg": float(tr[month]),
        "try_mom": _mom(tr, month),
        "peak_usd": peak,
        "peak_month": str(peak_month),
        "from_peak": usd_now / peak - 1,
        "crop_estimate_t": None,
        "crop_yoy": None,
        "crop_year": None,
    }
    if crop is not None and len(crop):
        est = crop.dropna(subset=["giresun_estimate_t"]).sort_values("year")
        if len(est):
            year = int(est["year"].iloc[-1])
            value = float(est["giresun_estimate_t"].iloc[-1])
            stats["crop_year"], stats["crop_estimate_t"] = year, value
            prev = est[est["year"] == year - 1]
            if len(prev) and prev["giresun_estimate_t"].iloc[0] > 0:
                stats["crop_yoy"] = value / float(prev["giresun_estimate_t"].iloc[0]) - 1
    return stats


def _as_of(df: pd.DataFrame) -> str | None:
    if "month" in df.columns and len(df):
        return str(df["month"].dropna().astype(str).max())
    if "year" in df.columns and len(df):
        return str(int(df["year"].max()))
    return None


def _previous_entries(out_dir: Path) -> dict:
    try:
        return json.loads((out_dir / "manifest.json").read_text(encoding="utf-8")).get("outputs", {})
    except Exception:
        return {}


def _stale_entry(prev: dict, name: str) -> dict:
    kept = prev.get(name)
    return {**kept, "stale": True} if kept else {"as_of": None, "rows": 0, "stale": True}


def write_site_data(crop: CropConfig, tables: dict, out_dir: Path, now: datetime) -> dict:
    out_dir = Path(out_dir)
    prev = _previous_entries(out_dir)
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    stats: dict | None = None

    for name, (builder, needs) in BUILDERS.items():
        missing = [k for k in needs if k not in tables]
        try:
            if missing:
                raise KeyError(f"missing tables: {missing}")
            frames[name] = builder(tables)
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"

    if "prices_monthly" in frames:
        try:
            frames["price_range"] = price_range(frames["prices_monthly"])
        except Exception as exc:
            errors["price_range"] = f"{type(exc).__name__}: {exc}"
        try:
            stats = stat_strip(frames["prices_monthly"], frames.get("crop_by_year"))
        except Exception as exc:
            errors["stats"] = f"{type(exc).__name__}: {exc}"
    else:
        errors.setdefault("price_range", "prices_monthly unavailable")
        errors.setdefault("stats", "prices_monthly unavailable")

    failed = [n for n in CORE_OUTPUTS if n in errors or (n != "stats" and n not in frames)]
    if failed or stats is None:
        raise SiteDataError(
            "core outputs failed: "
            + "; ".join(f"{n} ({errors.get(n, 'unavailable')})" for n in failed or ["stats"])
        )

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".site-data-", dir=out_dir.parent))
    try:
        entries: dict[str, dict] = {}
        written: list[str] = []
        for name, df in frames.items():
            df.to_csv(tmp / f"{name}.csv", index=False)
            written.append(f"{name}.csv")
            entries[name] = {"as_of": _as_of(df), "rows": int(len(df)), "stale": False}
        (tmp / "stats.json").write_text(json.dumps(stats, indent=2, allow_nan=False), encoding="utf-8")
        written.append("stats.json")
        entries["stats"] = {"as_of": stats["as_of"], "rows": 1, "stale": False}
        for name in BUILDERS:
            if name not in entries:
                entries[name] = _stale_entry(prev, name)
        manifest = {
            "crop": crop.slug,
            "built_at": now.astimezone(timezone.utc).isoformat(),
            "as_of": stats["as_of"],
            "outputs": entries,
        }
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        written.append("manifest.json")
        out_dir.mkdir(parents=True, exist_ok=True)
        for fname in written:
            os.replace(tmp / fname, out_dir / fname)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return manifest

"""Site data writer: builds the site tables, the price range and the stat strip, with fallback.

Everything crop-specific (input files, the local price column, the crop-estimate column, "as of"
overrides) comes from the crop's config and its module in ``hazelnut.site.crops``.
Each output is built fresh when its source tables are present and its builder succeeds.
Otherwise the last good file in ``out_dir`` is kept and marked ``stale`` in the manifest.
An output whose row count falls more than ``MAX_ROW_DROP`` below the previous build's counts
as failed (a partial source download), so it falls back the same way.
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

from hazelnut.forecast.dataset import DATA_DIR as INTERIM_DIR
from hazelnut.forecast.dataset import MANUAL_DIR
from hazelnut.forecast.intervals import LEVELS, column
from hazelnut.forecast.methods.baselines import EmpiricalNaive
from hazelnut.site.config import CropConfig, LocalCurrency
from hazelnut.site.crops import crop_module

CORE_OUTPUTS = ("prices_monthly", "price_range", "stats")
HORIZONS = (1, 3, 6)
MAX_ROW_DROP = 0.10  # a fresh output this much smaller than the last build is treated as failed


class SiteDataError(Exception):
    pass


def load_interim_tables(
    crop: CropConfig, interim_dir: Path = INTERIM_DIR, manual_dir: Path = MANUAL_DIR
) -> dict[str, pd.DataFrame]:
    """Read every input table of the crop (its ``INPUT_FILES``) that exists and parses; never raises."""
    folders = {"interim": Path(interim_dir), "manual": Path(manual_dir)}
    files = {key: folders[folder] / name for key, (folder, name) in crop_module(crop.slug).INPUT_FILES.items()}
    tables: dict[str, pd.DataFrame] = {}
    for key, path in files.items():
        try:
            if path.exists():
                tables[key] = pd.read_csv(path)
        except Exception:
            continue
    return tables


def _both(prices: pd.DataFrame, local_column: str) -> pd.DataFrame:
    return prices.dropna(subset=["usd_kg", local_column]).sort_values("month")


def price_range(prices: pd.DataFrame, local_column: str, horizons=HORIZONS) -> pd.DataFrame:
    """USD/kg quantiles (empirical naive) from the last month with both USD and local prices."""
    both = _both(prices, local_column)
    if both.empty:
        raise ValueError("no month with both USD and local prices")
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


def stat_strip(
    prices: pd.DataFrame, crop: pd.DataFrame | None, *, local: LocalCurrency, crop_col: str | None
) -> dict:
    """The stat strip. The local price keys follow the column: ``local.column``, ``local.mom_key``.

    ``crop_col`` is the ``crop`` column holding the crop estimate (None: no estimate).
    """
    both = _both(prices, local.column)
    if both.empty:
        raise ValueError("no month with both USD and local prices")
    month = pd.Period(both["month"].iloc[-1], "M")
    idx = pd.PeriodIndex(prices["month"], freq="M")
    usd = pd.Series(prices["usd_kg"].to_numpy(dtype=float), index=idx)
    tr = pd.Series(prices[local.column].to_numpy(dtype=float), index=idx)
    usd_now = float(usd[month])
    peak_month = usd[usd.index <= month].idxmax()
    peak = float(usd[peak_month])
    stats = {
        "as_of": str(month),
        "usd_kg": usd_now,
        "usd_mom": _mom(usd, month),
        local.column: float(tr[month]),
        local.mom_key: _mom(tr, month),
        "peak_usd": peak,
        "peak_month": str(peak_month),
        "from_peak": usd_now / peak - 1,
        "crop_estimate_t": None,
        "crop_yoy": None,
        "crop_year": None,
    }
    if crop_col and crop is not None and len(crop):
        est = crop.dropna(subset=[crop_col]).sort_values("year")
        if len(est):
            year = int(est["year"].iloc[-1])
            value = float(est[crop_col].iloc[-1])
            stats["crop_year"], stats["crop_estimate_t"] = year, value
            prev = est[est["year"] == year - 1]
            if len(prev) and prev[crop_col].iloc[0] > 0:
                stats["crop_yoy"] = value / float(prev[crop_col].iloc[0]) - 1
    return stats


def _as_of(name: str, df: pd.DataFrame, tables: dict, overrides: dict) -> str | None:
    if name in overrides:
        return overrides[name](tables)
    if name == "price_range":
        return str(df["from_month"].iloc[0]) if len(df) else None
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


def _row_drop(prev_entry: dict | None, rows: int) -> str | None:
    """Why a fresh output with ``rows`` rows is suspect against its previous entry, if it is."""
    prev_rows = (prev_entry or {}).get("rows") or 0
    if prev_rows and rows < prev_rows * (1 - MAX_ROW_DROP):
        return f"row count fell from {prev_rows} to {rows} (more than {MAX_ROW_DROP:.0%} below the last build)"
    return None


def _stale_entry(prev: dict, name: str) -> dict:
    kept = prev.get(name)
    return {**kept, "stale": True} if kept else {"as_of": None, "rows": 0, "stale": True}


def write_site_data(
    crop: CropConfig, tables: dict, out_dir: Path, now: datetime, notes: list[str] | None = None
) -> dict:
    """Build every output, write the files and the manifest, and return the manifest.

    ``notes``, if given, receives one line per output kept stale, with the reason.
    """
    out_dir = Path(out_dir)
    mod = crop_module(crop.slug)
    builders = mod.BUILDERS
    prev = _previous_entries(out_dir)
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    stats: dict | None = None

    for name, (builder, needs) in builders.items():
        missing = [k for k in needs if k not in tables]
        try:
            if missing:
                raise KeyError(f"missing tables: {missing}")
            frames[name] = builder(tables)
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"

    if "prices_monthly" in frames:
        try:
            frames["price_range"] = price_range(frames["prices_monthly"], crop.local_currency.column)
        except Exception as exc:
            errors["price_range"] = f"{type(exc).__name__}: {exc}"
        try:
            stats = stat_strip(frames["prices_monthly"], frames.get("crop_by_year"),
                               local=crop.local_currency, crop_col=getattr(mod, "STATS_CROP_COL", None))
        except Exception as exc:
            errors["stats"] = f"{type(exc).__name__}: {exc}"
    else:
        errors.setdefault("price_range", "prices_monthly unavailable")
        errors.setdefault("stats", "prices_monthly unavailable")

    for name in list(frames):
        drop = _row_drop(prev.get(name), len(frames[name]))
        if drop:
            errors[name] = drop
            del frames[name]

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
            entries[name] = {"as_of": _as_of(name, df, tables, getattr(mod, "AS_OF", {})), "rows": int(len(df)), "stale": False}
        (tmp / "stats.json").write_text(json.dumps(stats, indent=2, allow_nan=False), encoding="utf-8")
        written.append("stats.json")
        entries["stats"] = {"as_of": stats["as_of"], "rows": 1, "stale": False}
        for name in builders:
            if name not in entries:
                entries[name] = _stale_entry(prev, name)
                if notes is not None:
                    notes.append(f"{name}: {errors.get(name, 'unavailable')}")
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

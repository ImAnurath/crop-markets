"""Validation gate: fail the weekly site build when the data is broken or too old."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import pandas as pd

from hazelnut.site.site_data import CORE_OUTPUTS

FIRST_CONTIGUOUS = pd.Period("2005-01", "M")
NULLABLE_STATS = {"crop_estimate_t", "crop_yoy", "crop_year"}
PRICE_COLS = ("usd_kg", "try_kg", "usd_try")
RANGE_COLS = ("q05", "q10", "q50", "q90", "q95")
MAX_LAG_MONTHS = 3  # the as-of month may be at most this many months before today


def _finite_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _load_json(path: Path, problems: list[str]):
    if not path.exists():
        problems.append(f"{path.name}: missing")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        problems.append(f"{path.name}: unreadable ({e})")
        return None


def _load_csv(path: Path, problems: list[str]) -> pd.DataFrame | None:
    if not path.exists():
        problems.append(f"{path.name}: missing")
        return None
    try:
        return pd.read_csv(path)
    except Exception as e:  # noqa: BLE001 - any parse failure is a reported problem
        problems.append(f"{path.name}: unreadable ({e})")
        return None


def _check_prices(df: pd.DataFrame, as_of: pd.Period | None, problems: list[str]) -> None:
    missing = [c for c in ("month", *PRICE_COLS) if c not in df.columns]
    if missing:
        problems.append(f"prices_monthly.csv: missing columns {missing}")
        return
    try:
        months = pd.PeriodIndex(df["month"].astype(str), freq="M")
    except Exception:  # noqa: BLE001
        problems.append("prices_monthly.csv: unparseable month values")
        return
    df = df.assign(_m=months)
    if as_of is None:
        return
    span = df[(df["_m"] >= FIRST_CONTIGUOUS) & (df["_m"] <= as_of)]
    expected = pd.period_range(FIRST_CONTIGUOUS, as_of, freq="M")
    absent = [str(m) for m in expected.difference(pd.PeriodIndex(span["_m"]))]
    if absent:
        problems.append(f"prices_monthly.csv: missing months {', '.join(absent[:6])}")
    if span["_m"].duplicated().any():
        problems.append("prices_monthly.csv: duplicate months")
    for col in PRICE_COLS:
        vals = pd.to_numeric(span[col], errors="coerce")
        bad = span.loc[~(vals > 0) | ~vals.map(_finite_number), "_m"]
        if len(bad):
            problems.append(
                f"prices_monthly.csv: {col} missing or <= 0 in {len(bad)} month(s), first {bad.iloc[0]}"
            )


def _check_range(df: pd.DataFrame, problems: list[str]) -> None:
    missing = [c for c in RANGE_COLS if c not in df.columns]
    if missing:
        problems.append(f"price_range.csv: missing columns {missing}")
        return
    q = df[list(RANGE_COLS)].apply(pd.to_numeric, errors="coerce")
    if q.isna().any().any() or (q <= 0).any().any():
        problems.append("price_range.csv: NaN or non-positive quantile")
    elif not (q.diff(axis=1).iloc[:, 1:] >= 0).all().all():
        problems.append("price_range.csv: quantiles not ordered q05 <= ... <= q95")


def _check_stats(stats, problems: list[str]) -> None:
    if not isinstance(stats, dict):
        problems.append("stats.json: not an object")
        return
    for key, val in stats.items():
        if key == "as_of" or key == "peak_month":
            continue
        if val is None and key in NULLABLE_STATS:
            continue
        if isinstance(val, str):
            continue
        if not _finite_number(val):
            problems.append(f"stats.json: {key} is not a finite number ({val!r})")


def validate_site_data(out_dir: Path, today: date, max_lag_months: int = MAX_LAG_MONTHS) -> list[str]:
    """Return human-readable problems with the site data in `out_dir`; empty means OK."""
    out_dir = Path(out_dir)
    problems: list[str] = []

    manifest = _load_json(out_dir / "manifest.json", problems)
    stats = _load_json(out_dir / "stats.json", problems)
    prices = _load_csv(out_dir / "prices_monthly.csv", problems)
    prange = _load_csv(out_dir / "price_range.csv", problems)

    as_of = None
    if manifest is not None:
        try:
            as_of = pd.Period(str(manifest["as_of"]), "M")
        except Exception:  # noqa: BLE001
            problems.append("manifest.json: as_of missing or unparseable")
        outputs = manifest.get("outputs") if isinstance(manifest, dict) else None
        if not isinstance(outputs, dict):
            problems.append("manifest.json: outputs missing or not an object")
            outputs = {}
        for name in CORE_OUTPUTS:
            if name not in outputs:
                problems.append(f"manifest.json: no entry for core output {name}")
    if as_of is not None:
        cutoff = pd.Period(today, "M") - max_lag_months
        if as_of < cutoff:
            problems.append(f"manifest.json: as_of {as_of} is older than {max_lag_months} months before {today}")

    if prices is not None:
        _check_prices(prices, as_of, problems)
    if prange is not None:
        _check_range(prange, problems)
    if stats is not None:
        _check_stats(stats, problems)
    return problems

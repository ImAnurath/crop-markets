"""Build the public site's data tables for one crop (the weekly refresh runs this).

Writes <out>/<slug>/ (tables, stats.json, manifest.json, results/), then validates it.
results/ is scored from the crop's own committed backtest folder (its module's BACKTEST_DIR,
or --backtest); a crop without one gets no results tables.
Exit code: 0 ok, 1 if a core output cannot be built or validation finds problems.

Usage:
    python scripts/build_site_data.py [--crop hazelnut] [--interim data/interim] [--out site/data]
"""

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from hazelnut.forecast.dataset import MANUAL_DIR
from hazelnut.site.config import REPO_ROOT, SITE_DIR, load_crops
from hazelnut.site.crops import crop_module
from hazelnut.site.results import build_results
from hazelnut.site.site_data import SiteDataError, load_interim_tables, write_site_data
from hazelnut.site.validate import validate_site_data


def status(entry: dict) -> str:
    if entry.get("stale"):
        return "missing" if not entry.get("rows") and entry.get("as_of") is None else "stale"
    return "fresh"


def _write_summary(rows: list[tuple[str, str, str]], problems: list[str], notes: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = ["| output | status | as of |", "| --- | --- | --- |"]
    lines += [f"| {name} | {st} | {as_of} |" for name, st, as_of in rows]
    if notes:
        lines += ["", "### Not refreshed", ""] + [f"- {n}" for n in notes]
    lines += ["", "### Problems", ""]
    lines += [f"- {p}" for p in problems] or ["none"]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--crop", default="hazelnut")
    p.add_argument("--interim", type=Path, default=REPO_ROOT / "data" / "interim")
    p.add_argument("--manual", type=Path, default=MANUAL_DIR)
    p.add_argument("--out", type=Path, default=SITE_DIR / "data")
    p.add_argument("--backtest", type=Path, default=None,
                   help="backtest results folder (default: the crop module's BACKTEST_DIR)")
    p.add_argument("--today", type=date.fromisoformat, default=None, help="override today's date (tests)")
    args = p.parse_args(argv)

    crops = load_crops()
    if args.crop not in crops:
        print(f"unknown crop: {args.crop}")
        return 1
    crop = crops[args.crop]
    mod = crop_module(crop.slug)
    out_dir = args.out / crop.slug

    tables = load_interim_tables(crop, args.interim, args.manual)
    notes: list[str] = []
    try:
        manifest = write_site_data(crop, tables, out_dir, datetime.now(timezone.utc), notes=notes)
    except SiteDataError as exc:
        print(exc)
        return 1
    problems: list[str] = []
    backtest = args.backtest or getattr(mod, "BACKTEST_DIR", None)
    if backtest is None:
        print(f"results: {crop.slug} has no backtest folder, no results tables")
    else:
        try:
            build_results(backtest, out_dir / "results", getattr(mod, "CROP_CHECK_METHODS", None))
        except Exception as exc:
            problems.append(f"results build failed: {type(exc).__name__}: {exc}")

    rows = [(n, status(e), str(e.get("as_of") or "")) for n, e in manifest["outputs"].items()]
    for name, st, as_of in rows:
        print(f"{name}: {st}" + (f" (as of {as_of})" if as_of else ""))
    for note in notes:
        print(f"NOTE: {note}")

    problems += validate_site_data(crop, out_dir, args.today or datetime.now(timezone.utc).date())
    for problem in problems:
        print(f"PROBLEM: {problem}")
    _write_summary(rows, problems, notes)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

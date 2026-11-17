"""Build the public site's data tables for one crop (the weekly refresh runs this).

Writes <out>/<slug>/ (tables, stats.json, manifest.json, results/), then validates it.
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
from hazelnut.site.results import build_results
from hazelnut.site.site_data import SiteDataError, load_interim_tables, write_site_data
from hazelnut.site.validate import validate_site_data


def status(entry: dict) -> str:
    if entry.get("stale"):
        return "missing" if not entry.get("rows") and entry.get("as_of") is None else "stale"
    return "fresh"


def _write_summary(rows: list[tuple[str, str, str]]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = ["| output | status | as of |", "| --- | --- | --- |"]
    lines += [f"| {name} | {st} | {as_of} |" for name, st, as_of in rows]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--crop", default="hazelnut")
    p.add_argument("--interim", type=Path, default=REPO_ROOT / "data" / "interim")
    p.add_argument("--manual", type=Path, default=MANUAL_DIR)
    p.add_argument("--out", type=Path, default=SITE_DIR / "data")
    p.add_argument("--backtest", type=Path, default=REPO_ROOT / "reports" / "backtest")
    p.add_argument("--today", type=date.fromisoformat, default=None, help="override today's date (tests)")
    args = p.parse_args(argv)

    crops = load_crops()
    if args.crop not in crops:
        print(f"unknown crop: {args.crop}")
        return 1
    crop = crops[args.crop]
    out_dir = args.out / crop.slug

    tables = load_interim_tables(args.interim, args.manual)
    try:
        manifest = write_site_data(crop, tables, out_dir, datetime.now(timezone.utc))
    except SiteDataError as exc:
        print(exc)
        return 1
    build_results(args.backtest, out_dir / "results")

    rows = [(n, status(e), str(e.get("as_of") or "")) for n, e in manifest["outputs"].items()]
    for name, st, as_of in rows:
        print(f"{name}: {st}" + (f" (as of {as_of})" if as_of else ""))
    _write_summary(rows)

    problems = validate_site_data(out_dir, args.today or datetime.now(timezone.utc).date())
    for problem in problems:
        print(f"PROBLEM: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

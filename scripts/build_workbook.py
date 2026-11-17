"""Build the downloadable Excel workbook for one crop from its site data.

Usage:
    python scripts/build_workbook.py [--crop hazelnut]
Writes site/downloads/<slug>-market-data.xlsx from site/data/<slug>/.
"""

import argparse
import sys
from pathlib import Path

from hazelnut.site.config import SITE_DIR, load_crops
from hazelnut.site.workbook import build_workbook


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--crop", default="hazelnut")
    p.add_argument("--data", type=Path, default=SITE_DIR / "data", help="folder holding <slug>/")
    p.add_argument("--out", type=Path, default=SITE_DIR / "downloads")
    args = p.parse_args(argv)

    crops = load_crops()
    if args.crop not in crops:
        print(f"unknown crop: {args.crop}")
        return 1
    crop = crops[args.crop]
    args.out.mkdir(parents=True, exist_ok=True)
    path = build_workbook(args.data / crop.slug, args.out / f"{crop.slug}-market-data.xlsx", crop)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

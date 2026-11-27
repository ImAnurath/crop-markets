"""Build the downloadable Excel workbook for one crop from its site data, in every language.

Usage:
    python scripts/build_workbook.py [--crop hazelnut]             # every language
    python scripts/build_workbook.py [--crop hazelnut] --lang tr   # one language
Writes site/downloads/<slug>-market-data.xlsx (English) and
site/downloads/<slug>-market-data-<lang>.xlsx (each other language) from site/data/<slug>/.

The crop module reads its sheet names and headers in the active language when it is
imported, so each language other than this process's is built by running this script
again with SITE_LANG set.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from hazelnut.site import i18n
from hazelnut.site.config import SITE_DIR, load_crops
from hazelnut.site.workbook import build_workbook, workbook_filename


def _build_here(crop, data: Path, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    return build_workbook(data / crop.slug, out / workbook_filename(crop.slug), crop)


def _build_in_child(lang: str, args) -> int:
    env = {k: v for k, v in os.environ.items() if k != "QUARTO_PROFILE"}
    env["SITE_LANG"] = lang
    cmd = [sys.executable, str(Path(__file__).resolve()), "--crop", args.crop,
           "--data", str(args.data), "--out", str(args.out), "--lang", lang]
    return subprocess.run(cmd, env=env).returncode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--crop", default="hazelnut")
    p.add_argument("--data", type=Path, default=SITE_DIR / "data", help="folder holding <slug>/")
    p.add_argument("--out", type=Path, default=SITE_DIR / "downloads")
    p.add_argument("--lang", action="append", choices=i18n.LANGS,
                   help="build only this language (repeatable); default: all")
    args = p.parse_args(argv)

    crops = load_crops()
    if args.crop not in crops:
        print(f"unknown crop: {args.crop}")
        return 1
    crop = crops[args.crop]
    for lang in [code for code in i18n.LANGS if code in (args.lang or i18n.LANGS)]:
        if lang == i18n.LANG:
            print(f"wrote {_build_here(crop, args.data, args.out)}", flush=True)
        elif (code := _build_in_child(lang, args)) != 0:
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())

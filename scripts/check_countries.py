"""Warn about export destinations in the site data that have no ``country.*`` entry in
site/i18n (Ruling F1). Such a destination (a new or renamed UN Comtrade partner) shows
under its English name on the Turkish pages; that costs polish, not correctness, so the
weekly deploy carries on. Locally, tests/site/test_i18n.py still fails on it.

Each one is printed as a GitHub Actions ``::warning::`` line, and a line goes to the job
summary when ``GITHUB_STEP_SUMMARY`` is set. Always exits 0.

Usage:
    python scripts/check_countries.py [path/to/site/data]
"""

import os
import sys
from pathlib import Path

from hazelnut.site.i18n import missing_countries


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    missing = missing_countries(Path(args[0]) if args else None)
    for name in missing:
        print(f"::warning::export destination {name!r} has no country.* entry in "
              "site/i18n/en.yml and tr.yml; the Turkish pages show its English name")
    if missing:
        noun = "destination" if len(missing) == 1 else "destinations"
        line = (f"{len(missing)} export {noun} without a Turkish name (shown in English): "
                + ", ".join(missing))
    else:
        line = "Country names: every export destination has a Turkish name."
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Country names\n\n{line}\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

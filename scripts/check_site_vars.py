"""Fail when site/_variables.yml still holds placeholder owner details (run before deploy).

Exit code: 0 when every value is filled in, 1 otherwise (each problem is printed).

Usage:
    python scripts/check_site_vars.py [path/to/_variables.yml]
"""

import sys
from pathlib import Path

from hazelnut.site.site_vars import VARIABLES_FILE, check_site_vars


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else VARIABLES_FILE
    problems = check_site_vars(path)
    for problem in problems:
        print(f"PROBLEM: {problem}")
    if problems:
        print(f"{path} still has placeholder owner details; fill them in before deploying.")
        return 1
    print(f"{path.name}: owner details filled in")
    return 0


if __name__ == "__main__":
    sys.exit(main())

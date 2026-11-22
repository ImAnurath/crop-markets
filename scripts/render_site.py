"""Render the site in every language: English into site/_site/, Turkish into site/_site/tr/.

A full English render empties site/_site (Turkish tree included), so English always goes
first; rendering only Turkish leaves the English tree as it is. Use this instead of a
plain `quarto render site`, which renders English only.

Quarto is `quarto` on PATH unless the QUARTO variable names it. QUARTO_PYTHON defaults
to this interpreter, so run the script with the project venv.

Usage:
    python scripts/render_site.py               # English, then Turkish
    python scripts/render_site.py --lang tr     # Turkish only (English tree kept)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from hazelnut.site.i18n import LANGS

SITE = Path(__file__).resolve().parents[1] / "site"


def render_commands(quarto: str, langs: list[str]) -> list[list[str]]:
    """One `quarto render` per language, in LANGS order (English first)."""
    return [[quarto, "render", str(SITE), "--profile", lang] for lang in LANGS if lang in langs]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", action="append", choices=LANGS,
                        help="render only this language (repeatable); default: all")
    args = parser.parse_args(argv)
    env = {**os.environ, "QUARTO_PYTHON": os.environ.get("QUARTO_PYTHON") or sys.executable}
    for cmd in render_commands(os.environ.get("QUARTO") or "quarto", args.lang or list(LANGS)):
        print("+ " + " ".join(cmd), flush=True)
        code = subprocess.run(cmd, env=env).returncode
        if code:
            print(f"render failed (exit {code}): {' '.join(cmd)}", file=sys.stderr)
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())

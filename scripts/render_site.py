"""Render the site in every language: English into site/_site/, Turkish into site/_site/tr/.

A full English render empties site/_site (Turkish tree included), so English always goes
first; rendering only Turkish leaves the English tree as it is. Use this instead of a
plain `quarto render site`, which renders English only.

After the Turkish render, its robots.txt and 404.html are removed: GitHub Pages serves
only the root ones, and the root 404 page is bilingual. The root robots.txt gains the
Turkish sitemap. A tab title that names the site twice ("Ürün Piyasaları – Ürün
Piyasaları" on the Turkish home page, whose front-matter title is the English brand) is
cut to one.

Quarto is `quarto` on PATH unless the QUARTO variable names it. QUARTO_PYTHON defaults
to this interpreter, so run the script with the project venv.

Usage:
    python scripts/render_site.py               # English, then Turkish
    python scripts/render_site.py --lang tr     # Turkish only (English tree kept)
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from hazelnut.site.i18n import DEFAULT, LANGS

SITE = Path(__file__).resolve().parents[1] / "site"
ROOT_ONLY = ("robots.txt", "404.html")  # served from the site root only
# Quarto adds " – <site title>" to a page's tab title when the front-matter title is not the
# site title; it compares the title before filters/lang-meta.lua swaps in title-tr.
_TWICE = re.compile(r"<title>([^<]+?) – \1</title>")


def render_commands(quarto: str, langs: list[str]) -> list[list[str]]:
    """One `quarto render` per language, in LANGS order (English first)."""
    return [[quarto, "render", str(SITE), "--profile", lang] for lang in LANGS if lang in langs]


def finish_tree(site_dir: Path, lang: str) -> None:
    """Tidy a rendered non-default tree (site_dir/<lang>): move its sitemap line into the
    root robots.txt, drop the files only the root serves, and cut a tab title that names
    the site twice to one. Safe to run twice."""
    tree = Path(site_dir) / lang
    robots, root_robots = tree / "robots.txt", Path(site_dir) / "robots.txt"
    if robots.is_file() and root_robots.is_file():
        have = root_robots.read_text(encoding="utf-8").splitlines()
        new = [line for line in robots.read_text(encoding="utf-8").splitlines()
               if line.lower().startswith("sitemap:") and line not in have]
        if new:
            root_robots.write_text("\n".join(have + new) + "\n", encoding="utf-8")
    for name in ROOT_ONLY:
        (tree / name).unlink(missing_ok=True)
    for page in tree.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        fixed = _TWICE.sub(r"<title>\1</title>", text, count=1)
        if fixed != text:
            page.write_text(fixed, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", action="append", choices=LANGS,
                        help="render only this language (repeatable); default: all")
    args = parser.parse_args(argv)
    env = {**os.environ, "QUARTO_PYTHON": os.environ.get("QUARTO_PYTHON") or sys.executable}
    langs = args.lang or list(LANGS)
    for cmd in render_commands(os.environ.get("QUARTO") or "quarto", langs):
        print("+ " + " ".join(cmd), flush=True)
        code = subprocess.run(cmd, env=env).returncode
        if code:
            print(f"render failed (exit {code}): {' '.join(cmd)}", file=sys.stderr)
            return code
    for lang in langs:
        if lang != DEFAULT:
            finish_tree(SITE / "_site", lang)
    return 0


if __name__ == "__main__":
    sys.exit(main())

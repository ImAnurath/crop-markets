"""Snapshot the visible text of every page in a rendered English site tree.

Each page becomes one text file: its visible text with scripts, styles and SVG dropped,
and hidden elements too (the ``hidden`` attribute or class, such as Quarto's folded
``cell-code hidden`` source blocks), one line per block element and whitespace collapsed. Alt text, aria-labels, titles and
placeholders count as visible too (each on its own line, marked ``[alt]`` and so on).
The Turkish tree (``tr/``) is skipped. ``tests/site/fixtures/en_text/`` holds the English
snapshot that the rendered site must keep matching (tests/site/test_rendered_text.py).

Usage:
    python scripts/snapshot_text.py SITE_DIR [OUT_DIR]

OUT_DIR defaults to tests/site/fixtures/en_text. Files in OUT_DIR are replaced.
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "tests" / "site" / "fixtures" / "en_text"
SKIP_TREES = ("tr",)

DROPPED = {"script", "style", "svg", "noscript", "template", "head"}
BLOCKS = {
    "address", "article", "aside", "blockquote", "br", "caption", "dd", "details", "div",
    "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
    "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "option", "p", "pre",
    "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}
TEXT_ATTRS = ("alt", "aria-label", "title", "placeholder", "data-scroll-hint")
_WS = re.compile(r"\s+")


def _hidden(attrs) -> bool:
    """True for an element never shown: a ``hidden`` attribute or a ``hidden`` class."""
    for name, value in attrs:
        if name == "hidden" or (name == "class" and "hidden" in (value or "").split()):
            return True
    return False


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._buf: list[str] = []
        self._drop_tag: str | None = None  # the element being dropped
        self._dropped = 0  # nesting depth of that tag inside it

    def _flush(self) -> None:
        line = _WS.sub(" ", "".join(self._buf)).strip()
        if line:
            self.lines.append(line)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if self._dropped:
            if tag == self._drop_tag:
                self._dropped += 1
            return
        if tag not in VOID and (tag in DROPPED or _hidden(attrs)):
            self._drop_tag, self._dropped = tag, 1
            return
        if tag in BLOCKS:
            self._flush()
        for name, value in attrs:
            if name in TEXT_ATTRS and value and value.strip():
                self._flush()
                self.lines.append(f"[{name}] {_WS.sub(' ', value).strip()}")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self._dropped and tag == self._drop_tag:
            self._dropped -= 1

    def handle_endtag(self, tag):
        if self._dropped:
            if tag == self._drop_tag:
                self._dropped -= 1
            return
        if tag in BLOCKS:
            self._flush()

    def handle_data(self, data):
        if not self._dropped:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def page_text(html: str) -> str:
    """The visible text of one HTML page, one line per block, ending in a newline."""
    parser = _Text()
    parser.feed(html)
    parser.close()
    return "".join(line + "\n" for line in parser.lines)


def snapshot_name(rel: str) -> str:
    """``hazelnut/analyses/forecasting.html`` -> ``hazelnut__analyses__forecasting.txt``."""
    return rel.removesuffix(".html").replace("/", "__") + ".txt"


def site_texts(site_dir: Path) -> dict[str, str]:
    """{snapshot file name: page text} for every English page under ``site_dir``."""
    site_dir = Path(site_dir)
    out = {}
    for path in sorted(site_dir.rglob("*.html")):
        rel = path.relative_to(site_dir).as_posix()
        if rel.split("/", 1)[0] in SKIP_TREES:
            continue
        out[snapshot_name(rel)] = page_text(path.read_text(encoding="utf-8"))
    return out


def write_snapshot(site_dir: Path, out_dir: Path) -> int:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.txt"):
        old.unlink()
    texts = site_texts(site_dir)
    for name, text in texts.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    return len(texts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site_dir", type=Path, help="a rendered site tree, e.g. site/_site")
    ap.add_argument("out_dir", type=Path, nargs="?", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    if not args.site_dir.is_dir():
        print(f"not a directory: {args.site_dir}", file=sys.stderr)
        return 2
    n = write_snapshot(args.site_dir, args.out_dir)
    print(f"wrote {n} page snapshots to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

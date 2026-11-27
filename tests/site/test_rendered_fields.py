"""No unfilled ``{field}`` from an i18n template on a rendered page, in either language
tree: a template whose field was never given (``t("…{value}…")`` without ``value=``)
would show its braces to the reader.

Every visible text node and every attribute value is scanned. Skipped, because braces are
legitimate there and nobody reads them: ``<script>`` and ``<style>`` (Plotly's JSON, OJS,
CSS) and hidden elements (the ``hidden`` attribute or class, as scripts/snapshot_text.py
reads it), such as Quarto's folded OJS source.
"""

import re
from html.parser import HTMLParser

import pytest

from hazelnut.site.config import SITE_DIR
from tests.site.test_turkish_text import snapshot

RENDERED = SITE_DIR / "_site"
# Written into site/_site by scripts/i18n_review.py for the owner (it shows the templates
# with their fields on purpose); never rendered or deployed.
LOCAL_ONLY = ("i18n-review.html",)
FIELD = re.compile(r"\{[a-z_]+\}")
SKIPPED = {"script", "style"}


class _Fields(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []
        self._skip_tag: str | None = None  # the element being skipped
        self._skipped = 0  # nesting depth of that tag inside it

    def handle_starttag(self, tag, attrs):
        if self._skipped:
            self._skipped += tag == self._skip_tag
            return
        if tag in SKIPPED or snapshot._hidden(attrs):
            if tag not in snapshot.VOID:  # a void element has no contents to skip
                self._skip_tag, self._skipped = tag, 1
            return
        for name, value in attrs:
            self.found.extend(f"<{tag} {name}> {m}" for m in FIELD.findall(value or ""))

    def handle_endtag(self, tag):
        if self._skipped and tag == self._skip_tag:
            self._skipped -= 1

    def handle_data(self, data):
        if not self._skipped:
            self.found.extend(f"text {m}" for m in FIELD.findall(data))


def unfilled_fields(html: str) -> list[str]:
    """Each ``{field}`` left in the page's visible text or attributes (scripts, styles and
    hidden elements skipped)."""
    parser = _Fields()
    parser.feed(html)
    parser.close()
    return parser.found


def test_unfilled_fields_finds_text_and_attributes_but_not_scripts():
    html = ('<p title="Up {value}">Price {as_of} &#123;month&#125;</p>'
            '<script type="application/json">{"a": "{value}"}</script>'
            '<style>.x{color:red}</style><p>%{y:.2f} {Not} {a1} done</p>'
            '<div class="cell-code hidden"><div><pre>{name}</pre></div></div>'
            '<input hidden value="{kept}"><p>{after}</p>')
    assert unfilled_fields(html) == ["<p title> {value}", "text {as_of}", "text {month}",
                                    "text {after}"]


@pytest.mark.skipif(not RENDERED.is_dir(), reason="site/_site not rendered (run scripts/render_site.py)")
def test_rendered_pages_have_no_unfilled_fields():
    pages = [p for p in sorted(RENDERED.rglob("*.html")) if p.name not in LOCAL_ONLY]
    assert any(p.relative_to(RENDERED).parts[0] == "tr" for p in pages), "no Turkish tree"
    problems = {p.relative_to(RENDERED).as_posix(): found for p in pages
                if (found := unfilled_fields(p.read_text(encoding="utf-8")))}
    assert problems == {}

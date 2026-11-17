"""Number formats and small HTML fragments for the site's overview and home pages.

Pages call these from Python cells and emit the HTML as a raw block (see ``raw_html``).
Nothing here assumes a crop or a country: the page passes in its labels.
"""
from __future__ import annotations

import calendar
import json
import math
from html import escape
from pathlib import Path
from typing import Mapping

from hazelnut.site.config import CropConfig

NA = "n/a"
MINUS = "−"
ARROW = '<svg class="ico" aria-hidden="true"><use href="#arrow-right"/></svg>'


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def fmt_usd(x) -> str:
    """US dollars with two decimals: ``$4.28``."""
    return NA if _missing(x) else f"${x:,.2f}"


def fmt_number(x) -> str:
    """A price in another currency, two decimals: ``208.15`` (the page adds the unit)."""
    return NA if _missing(x) else f"{x:,.2f}"


def fmt_change(x) -> str:
    """A fractional change as a signed percent with one decimal: ``−5.3%``, ``+31.5%``."""
    if _missing(x):
        return NA
    pct = round(x * 100, 1)
    if pct == 0:
        return "0.0%"
    return f"{'+' if pct > 0 else MINUS}{abs(pct):.1f}%"


def fmt_tonnes(x) -> str:
    """Tonnes with thousands separators: ``86,440``."""
    return NA if _missing(x) else f"{round(x):,}"


def _parse(as_of: str) -> tuple[int, int | None]:
    """``"2026-09"`` -> (2026, 9); a yearly ``"2026"`` -> (2026, None)."""
    year, _, month = str(as_of).partition("-")
    return int(year), (int(month) if month else None)


def month_label(as_of: str) -> str:
    """``"2026-09"`` -> ``"September 2026"``; a yearly ``"2026"`` stays ``"2026"``."""
    year, month = _parse(as_of)
    return str(year) if month is None else f"{calendar.month_name[month]} {year}"


def previous_month_name(as_of: str) -> str:
    """The month before ``as_of`` by name: ``"2026-01"`` -> ``"December"``."""
    _, month = _parse(as_of)
    return calendar.month_name[12 if month == 1 else month - 1]


def as_of_stamp(manifest: Mapping) -> str:
    """"Data as of <Month YYYY> · refreshed weekly", plus the oldest stale source if any."""
    stamp = f"Data as of {month_label(manifest['as_of'])} · refreshed weekly"
    stale = [o["as_of"] for o in manifest.get("outputs", {}).values() if o.get("stale")]
    if stale:
        # A yearly as_of counts as the start of its year (month 0) when ordering.
        oldest = min(stale, key=lambda a: (_parse(a)[0], _parse(a)[1] or 0))
        stamp += f" (some sources from {month_label(oldest)})"
    return stamp


def market_meta_html(manifest: Mapping) -> str:
    """The row above the stat strip: "The market this month" and the as-of stamp."""
    return (
        '<div class="meta"><span class="eyebrow">The market this month</span>'
        f'<span class="live"><i aria-hidden="true"></i>{escape(as_of_stamp(manifest))}</span></div>'
    )


def load_page_data(data_dir: Path) -> tuple[dict, dict]:
    """``stats.json`` and ``manifest.json`` from one crop's site data folder."""
    data_dir = Path(data_dir)
    read = lambda name: json.loads((data_dir / name).read_text(encoding="utf-8"))  # noqa: E731
    return read("stats.json"), read("manifest.json")


def _change_span(x) -> str:
    cls = ' class="down"' if not _missing(x) and fmt_change(x).startswith(MINUS) else ""
    return f"<span{cls}>{fmt_change(x)}</span>"


def _stat(label: str, value_html: str, sub_html: str) -> str:
    return (
        f'<div class="stat"><span class="eyebrow">{label}</span>'
        f'<div class="v">{value_html}</div><div class="s">{sub_html}</div></div>'
    )


def market_strip_html(stats: Mapping, *, local_name: str, local_unit: str, crop_source: str) -> str:
    """The four-stat "market this month" strip.

    ``local_name`` names the local currency in the label ("Price, lira"), ``local_unit``
    is its unit ("TL" -> "TL/kg"), ``crop_source`` says whose crop estimate it is.
    """
    name, unit, source = escape(local_name), escape(local_unit), escape(crop_source)
    prev = previous_month_name(stats["as_of"])

    if _missing(stats.get("from_peak")) or _missing(stats.get("peak_usd")) or not stats.get("peak_month"):
        peak_sub = "peak n/a"
    else:
        peak_sub = f"since {month_label(stats['peak_month'])} ({fmt_usd(stats['peak_usd'])})"

    year = stats.get("crop_year")
    estimate = stats.get("crop_estimate_t")
    if _missing(estimate):
        crop_value, crop_sub = NA, f"{source}, no estimate yet"
    else:
        crop_value = f"{fmt_tonnes(estimate)}<small> t</small>"
        if _missing(stats.get("crop_yoy")) or _missing(year):
            crop_sub = f"{source}, no earlier year to compare"
        else:
            crop_sub = f"{source}, {_change_span(stats['crop_yoy'])} on {int(year) - 1}"
    crop_label = "Crop estimate" if _missing(year) else f"{int(year)} crop estimate"

    usd = fmt_usd(stats.get("usd_kg"))
    local = fmt_number(stats.get("try_kg"))
    stats_html = [
        _stat("Price, USD", usd + ("" if usd == NA else "<small> /kg</small>"),
              f"{_change_span(stats.get('usd_mom'))} on {prev}"),
        _stat(f"Price, {name}", local + ("" if local == NA else f"<small> {unit}/kg</small>"),
              f"{_change_span(stats.get('try_mom'))} on {prev}"),
        _stat("From the peak", fmt_change(stats.get("from_peak")), peak_sub),
        _stat(crop_label, crop_value, crop_sub),
    ]
    return '<div class="strip">' + "".join(stats_html) + "</div>"


def exchanges_phrase(exchanges) -> str:
    """("Giresun", "Ordu") -> "Giresun & Ordu exchanges"."""
    names = list(exchanges)
    if len(names) == 1:
        return f"{names[0]} exchange"
    return f"{', '.join(names[:-1])} & {names[-1]} exchanges"


def crop_cards_html(crops: Mapping[str, CropConfig], data_dir: Path) -> str:
    """One card per crop for the home page, each linking ``<slug>/index.qmd``.

    Shows the latest USD price when the crop's ``stats.json`` exists under ``data_dir``.
    """
    cards = []
    for crop in crops.values():
        price = ""
        stats_file = Path(data_dir) / crop.slug / "stats.json"
        if stats_file.exists():
            stats = json.loads(stats_file.read_text(encoding="utf-8"))
            if not _missing(stats.get("usd_kg")):
                price = (
                    f'<p>{fmt_usd(stats["usd_kg"])}/kg in {month_label(stats["as_of"])}</p>'
                )
        where = escape(f"{crop.country} · {exchanges_phrase(crop.exchanges)}")
        cards.append(
            f'<a class="panel crop-card" href="{escape(crop.slug)}/index.qmd">'
            f'<span class="eyebrow">{where}</span>'
            f"<h3>{escape(crop.name)} {ARROW}</h3>{price}</a>"
        )
    return '<div class="crops">' + "".join(cards) + "</div>"


def raw_html(html: str) -> None:
    """Display ``html`` in a Quarto page as a raw HTML block (no text/html output, see
    ``charts.show``)."""
    import IPython.display

    IPython.display.display(IPython.display.Markdown("```{=html}\n" + html + "\n```\n"))

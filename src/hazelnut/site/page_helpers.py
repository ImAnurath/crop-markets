"""Number formats, small HTML fragments and computed takeaways for the site's pages
(home, overview, dashboard).

Pages call these from Python cells and emit the HTML as a raw block (see ``raw_html``).
Nothing here assumes a crop or a country: the page passes in its labels.
"""
from __future__ import annotations

import calendar
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Mapping

import pandas as pd

from hazelnut.site.config import CropConfig
from hazelnut.site.labels import OTHER_PARTNER, method_name

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


EXCHANGE_SUFFIX = " Commodity Exchange"


def sources_summary(sources) -> tuple[str, str]:
    """("8 public datasets", "Giresun & Ordu exchanges, UN Comtrade, ...") from a crop's
    ``WORKBOOK_SOURCES`` rows (provider name first). Commodity exchanges are grouped."""
    names = [row[0] for row in sources]
    cities = [n.removesuffix(EXCHANGE_SUFFIX) for n in names if n.endswith(EXCHANGE_SUFFIX)]
    others = [n for n in names if not n.endswith(EXCHANGE_SUFFIX)]
    listed = ([exchanges_phrase(cities)] if cities else []) + others
    count = f"{len(names)} public dataset{'' if len(names) == 1 else 's'}"
    return count, ", ".join(listed)


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


# --- Dashboard --------------------------------------------------------------------------
# Panel loading with an error state, and each panel's takeaway, computed from the data.

UNAVAILABLE = "This chart's data is not available in this refresh."


def read_csv_or_none(path: Path, required: Sequence[str] = ()) -> pd.DataFrame | None:
    """The CSV at ``path``, or None if it is missing, unreadable, has no rows, or lacks
    any ``required`` column. The page then shows ``unavailable_html()`` in that panel."""
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if df.empty or any(c not in df.columns for c in required):
        return None
    return df


def read_json_or_none(path: Path) -> dict | None:
    """The JSON object at ``path``, or None if it is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def unavailable_html() -> str:
    """The panel body shown when its data file is missing or unreadable."""
    return f'<div class="chart-error" role="note">{escape(UNAVAILABLE, quote=False)}</div>'


def panel_head_html(title: str, sub: str) -> str:
    """A dashboard panel's title and its one-line takeaway."""
    return (f'<h2 class="ptitle">{escape(title, quote=False)}</h2>'
            f'<div class="sub">{escape(sub, quote=False)}</div>')


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _join_names(names: Sequence[str]) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


@dataclass(frozen=True)
class ShockMove:
    low_month: str
    low: float
    peak_month: str
    peak: float

    @property
    def months(self) -> int:
        return (pd.Period(self.peak_month, "M") - pd.Period(self.low_month, "M")).n


def shock_move(prices: pd.DataFrame, start: str, end: str, col: str = "usd_kg") -> ShockMove | None:
    """The price's run-up in a shock window: the peak, and the lowest price before it."""
    s = prices.dropna(subset=[col])
    s = pd.Series(s[col].to_numpy(dtype=float), index=s["month"].astype(str)).sort_index()
    w = s[(s.index >= start) & (s.index <= end)]
    if w.empty:
        return None
    peak_month = str(w.idxmax())
    before = w[w.index <= peak_month]
    low_month = str(before.idxmin())
    return ShockMove(low_month, float(before[low_month]), peak_month, float(w[peak_month]))


def price_subtitle(prices: pd.DataFrame, named_shocks: Sequence[tuple[str, tuple[str, str]]]) -> str:
    """"The 2014 frost took the price from $2.92 to $7.59 in 14 months; ..." from the data.

    ``named_shocks`` pairs the page's name for a shock with its (first, last) month."""
    parts = []
    for name, (start, end) in named_shocks:
        m = shock_move(prices, start, end)
        if m is None:
            continue
        lead = f"{name} took the price from" if not parts else f"{name}, from"
        parts.append(f"{lead} {fmt_usd(m.low)} to {fmt_usd(m.peak)} "
                     f"in {_plural(m.months, 'month')}")
    if not parts:
        return "Monthly exchange price; shaded periods are supply shocks."
    text = "; ".join(parts) + "."
    return text[0].upper() + text[1:]


def shock_years_label(shocks: Sequence[tuple[str, str]]) -> str:
    """[("2005-01", "2005-12"), ("2014-01", "2015-12")] -> "2005 and 2014-15"."""
    def years(a: str, b: str) -> str:
        ya, yb = a[:4], b[:4]
        if ya == yb:
            return ya
        return f"{ya}-{yb[2:]}" if ya[:2] == yb[:2] else f"{ya}-{yb}"
    return _join_names([years(a, b) for a, b in shocks])


def range_subtitle(rng: pd.DataFrame) -> str:
    """The 8-in-10 band at the longest horizon, in words."""
    row = rng.sort_values("horizon").iloc[-1]
    return (f"If past {int(row['horizon'])}-month moves repeat, eight times in ten the "
            f"{month_label(str(row['target_month']))} price lands between "
            f"{fmt_usd(float(row['q10']))} and {fmt_usd(float(row['q90']))}.")


def range_coverage_note(ranges: pd.DataFrame | None, method: str, horizon: int) -> str | None:
    """How often the 8-in-10 band held in the backtest (``results/ranges.csv``), or None."""
    if ranges is None or not {"method", "horizon", "cov80"} <= set(ranges.columns):
        return None
    hit = ranges[(ranges["method"] == method) & (ranges["horizon"] == horizon)]
    if hit.empty or _missing(float(hit["cov80"].iloc[0])):
        return None
    return (f"In testing, the 8-in-10 band held {round(float(hit['cov80'].iloc[0]) * 100)}% "
            f"of the time at {_plural(horizon, 'month')}.")


def range_currencies_label(currencies: Sequence[str]) -> str:
    """crops.yml ``range_currencies`` as shown on the page: ("usd",) -> "USD"."""
    return ", ".join(c.upper() for c in currencies)


def exports_subtitle(top: pd.DataFrame, period_end: str, n: int = 2) -> str:
    """"Italy and Germany took 51% of export volume in the 12 months to December 2025."
    The "Other" bucket is never named as a destination."""
    named = top[top["partner"] != OTHER_PARTNER].sort_values("share", ascending=False).head(n)
    share = round(float(named["share"].sum()) * 100)
    return (f"{_join_names(named['partner'].astype(str))} took {share}% of export volume "
            f"in the 12 months to {period_end}.")


def season_months(prices: pd.DataFrame, season: str) -> list[str]:
    """The months of ``season`` that have a price, in order."""
    return sorted(prices.loc[prices["season"] == season, "month"].astype(str))


def season_to_date_note(prices: pd.DataFrame, season: str) -> str | None:
    """A note for a season with fewer than 12 priced months, else None."""
    months = season_months(prices, season)
    if not months or len(months) >= 12:
        return None
    first, last = months[0], months[-1]
    if first == last:
        span = f"{month_label(first)} only"
    elif first[:4] == last[:4]:
        span = f"{calendar.month_name[int(first[5:])]} to {month_label(last)}"
    else:
        span = f"{month_label(first)} to {month_label(last)}"
    return f"{season} is season to date ({span}), so its average is provisional."


def correlation_words(r: float) -> str:
    """Plain words for a crop-size / price correlation."""
    if r <= -0.4:
        return "bigger crops have usually come with lower prices"
    if r <= -0.2:
        return "bigger crops have loosely gone with lower prices"
    if r < 0.2:
        return "crop size alone says little about the price"
    return "bigger crops have not come with lower prices"


MIN_SEASONS = 3


def crop_price_subtitle(crop: pd.DataFrame, x_col: str, exclude_season: str | None = None) -> str:
    """The crop-size / season-price link over complete seasons, in words with the r."""
    df = crop.dropna(subset=[x_col, "season_avg_usd"])
    if exclude_season is not None:
        df = df[df["season"] != exclude_season]
    if len(df) < MIN_SEASONS:
        return "Crop estimate against the season's average price."
    r = float(df[x_col].corr(df["season_avg_usd"]))
    r_text = f"{r:.2f}".replace("-", MINUS)
    return f"Over {len(df)} seasons, {correlation_words(r)} (correlation {r_text})."


def crop_panel(crop: pd.DataFrame, x_col: str,
               prices: pd.DataFrame | None) -> tuple[pd.DataFrame, str, str | None]:
    """Chart data, subtitle and note for the crop-vs-price panel.

    When the latest plotted season is still in progress (fewer than 12 priced months in
    ``prices``), its chart label gets "to date", it is left out of the correlation, and
    the note says so. Returns a copy; ``crop`` is not changed."""
    df = crop.copy()
    complete = df.dropna(subset=[x_col, "season_avg_usd"]).sort_values("year")
    note = None
    partial = None
    if not complete.empty and prices is not None:
        latest = str(complete["season"].iloc[-1])
        note = season_to_date_note(prices, latest)
        if note is not None:
            partial = latest
            df.loc[df["season"] == latest, "season"] = f"{latest} to date"
    return df, crop_price_subtitle(crop, x_col, exclude_season=partial), note


NAIVE = "naive"


def _ratios(board: pd.DataFrame) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for rec in board.itertuples(index=False):
        out.setdefault(str(rec.method), {})[int(rec.horizon)] = float(rec.ratio)
    return out


def scoreboard_rows(board: pd.DataFrame) -> list[tuple[str, str, dict[int, float]]]:
    """(method, readable name, {horizon: ratio}); naive first, then by mean ratio."""
    ratios = _ratios(board)
    order = sorted(ratios, key=lambda m: (m != NAIVE, sum(ratios[m].values()) / len(ratios[m])))
    return [(m, method_name(m), ratios[m]) for m in order]


def scoreboard_subtitle(board: pd.DataFrame) -> str:
    """The takeaway: how many method-horizon scores came in under naive (usually none)."""
    others = board[board["method"] != NAIVE]
    under = int((others["ratio"] < 1).sum())
    lead = ("Each method's error divided by naive's (the price stays where it is): "
            "above 1 is worse.")
    if under == 0:
        return f"{lead} None beat naive at any horizon."
    return (f"{lead} {under} of {len(others)} method-horizon scores came in under 1; "
            "the forecasting analysis tests whether that is more than chance.")


HOLDOUT_NOTE = "scored once, never tuned on"


def _holdout_sentence(holdout: pd.DataFrame) -> str:
    under = [name for m, name, r in scoreboard_rows(holdout)
             if m != NAIVE and r and all(v < 1 for v in r.values())]
    who = (f"{_join_names(under)} came in under naive at every horizon" if under
           else "no method beat naive at every horizon")
    return f"Holdout ({HOLDOUT_NOTE}): {who}."


def scoreboard_html(dev: pd.DataFrame, holdout: pd.DataFrame | None, analysis_href: str) -> str:
    """The dev scoreboard as a table (naive row in amber) and its footnote."""
    horizons = sorted(int(h) for h in dev["horizon"].unique())
    head = "".join(f'<th class="n" scope="col">{h} mo</th>' for h in horizons)
    body = []
    for m, name, r in scoreboard_rows(dev):
        cls = ' class="hl"' if m == NAIVE else ""
        cells = "".join(f'<td class="n">{r[h]:.2f}</td>' if h in r else '<td class="n">n/a</td>'
                        for h in horizons)
        body.append(f"<tr{cls}><td>{escape(name)}</td>{cells}</tr>")
    nmin, nmax = int(dev["n"].min()), int(dev["n"].max())
    count = f"{nmin}" if nmin == nmax else f"{nmin} to {nmax}"
    foot = f"Ratio of mean absolute errors, over {count} forecasts per horizon."
    if holdout is not None and not holdout.empty:
        foot += " " + _holdout_sentence(holdout)
    foot += f' <a href="{escape(analysis_href)}">Forecasting analysis</a>'
    return (
        # Quarto restyles raw HTML tables (striped, visible caption) unless told not to.
        '<table class="scoreboard" data-quarto-disable-processing="true">'
        '<caption class="visually-hidden">Forecast error relative to naive, by months ahead'
        "</caption>"
        f'<thead><tr><th scope="col">Method</th>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table>"
        f'<p class="foot">{foot}</p>'
    )

"""Number formats, small HTML fragments and computed takeaways for the site's pages
(home, overview, dashboard, analyses).

Pages call these from Python cells and emit the HTML as a raw block (see ``raw_html``).
Nothing here assumes a crop or a country: the page passes in its labels.
"""
from __future__ import annotations

import calendar
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
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


def partial_season(crop: pd.DataFrame, x_col: str, prices: pd.DataFrame | None) -> str | None:
    """The latest season with both a crop size and an average price, if it is still in
    progress (fewer than 12 priced months in ``prices``); else None."""
    complete = crop.dropna(subset=[x_col, "season_avg_usd"]).sort_values("year")
    if complete.empty or prices is None:
        return None
    latest = str(complete["season"].iloc[-1])
    return latest if season_to_date_note(prices, latest) is not None else None


def crop_panel(crop: pd.DataFrame, x_col: str,
               prices: pd.DataFrame | None) -> tuple[pd.DataFrame, str, str | None]:
    """Chart data, subtitle and note for the crop-vs-price panel.

    When the latest plotted season is still in progress (fewer than 12 priced months in
    ``prices``), its chart label gets "to date", it is left out of the correlation, and
    the note says so. Returns a copy; ``crop`` is not changed."""
    df = crop.copy()
    partial = partial_season(crop, x_col, prices)
    note = None
    if partial is not None:
        note = season_to_date_note(prices, partial)
        df.loc[df["season"] == partial, "season"] = f"{partial} to date"
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


# --- Analyses ---------------------------------------------------------------------------
# The analyses pages: index cards, page head, and each panel's takeaway or table, computed
# from the site data. Labels (crop, exchange and method names) come from the page.

def _r_text(r: float) -> str:
    return f"{r:.2f}".replace("-", MINUS)


def count_text(n: pd.Series) -> str:
    lo, hi = int(n.min()), int(n.max())
    return f"{lo}" if lo == hi else f"{lo} to {hi}"


def analyses_list_html(slugs: Sequence[str], entries: Mapping[str, tuple[str, str]]) -> str:
    """One card per analysis, in ``slugs`` order (crops.yml ``analyses``), each linking
    ``<slug>.qmd``. ``entries`` maps a slug to (title, one-line summary); a slug without an
    entry still gets a card, titled from the slug."""
    cards = []
    for slug in slugs:
        title, summary = entries.get(slug, (slug.replace("-", " ").capitalize(), ""))
        text = f"<p>{escape(summary, quote=False)}</p>" if summary else ""
        cards.append(f'<a class="panel analysis-card" href="{escape(slug)}.qmd">'
                     f"<h3>{escape(title, quote=False)} {ARROW}</h3>{text}</a>")
    return '<nav class="analyses" aria-label="Analyses">' + "".join(cards) + "</nav>"


def analysis_head_html(crop_name: str, page: str, h1: str, found: str,
                       stamp: str | None = None) -> str:
    """An analysis page's head: eyebrow (with a link back to the analyses list), h1, the
    optional as-of stamp, and the "What we found" paragraph."""
    live = (f'<span class="live"><i aria-hidden="true"></i>{escape(stamp, quote=False)}</span>'
            if stamp else "")
    return (
        '<div class="dash-head"><div>'
        f'<span class="eyebrow">Crops / {escape(crop_name)} / '
        f'<a href="index.qmd">Analyses</a> / {escape(page)}</span>'
        f"<h1>{escape(h1, quote=False)}</h1></div>{live}</div>"
        '<div class="found"><span class="eyebrow">What we found</span>'
        f"<p>{escape(found, quote=False)}</p></div>"
    )


# Seasonality

def seasonal_profile(prices: pd.DataFrame, col: str = "usd_kg") -> pd.DataFrame:
    """Each month's price as a change from its season's mean, over complete seasons (all
    12 months priced), summarised by position in the season.

    Columns: ``month`` (calendar month number), ``label`` (month name), ``mean``, ``q25``,
    ``q75`` (fractions; the middle half of seasons) and ``seasons`` (how many)."""
    df = prices[["month", "season", col]].copy()
    df["month"] = df["month"].astype(str)
    priced = df.dropna(subset=[col]).groupby("season")[col].count()
    df = df[df["season"].isin(priced[priced == 12].index)].sort_values("month")
    cols = ["month", "label", "mean", "q25", "q75", "seasons"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["dev"] = df[col] / df.groupby("season")[col].transform("mean") - 1
    df["pos"] = df.groupby("season").cumcount()
    g = df.groupby("pos")
    out = pd.DataFrame({
        "month": g["month"].first().str[5:].astype(int),
        "mean": g["dev"].mean(), "q25": g["dev"].quantile(0.25),
        "q75": g["dev"].quantile(0.75), "seasons": g["dev"].count(),
    })
    out["label"] = out["month"].map(lambda m: calendar.month_name[m])
    return out.reset_index(drop=True)[cols]


def seasonality_subtitle(profile: pd.DataFrame) -> str:
    """The lowest and highest month on average, and how wide seasons spread around it."""
    lo = profile.loc[profile["mean"].idxmin()]
    hi = profile.loc[profile["mean"].idxmax()]
    spread = round(float((profile["q75"] - profile["q25"]).median()) * 100)
    return (f"Across {int(profile['seasons'].max())} complete seasons, the average month sits "
            f"between {fmt_change(lo['mean'])} ({lo['label']}) and {fmt_change(hi['mean'])} "
            f"({hi['label']}) from its season's mean; the middle half of seasons spans "
            f"{spread} points in a typical month.")


# Exports

def yearly_shares(exports: pd.DataFrame, product: str, top: int = 5,
                  exclude: Sequence[str] = ("World",)) -> pd.DataFrame:
    """Each partner's share of ``product`` export volume by calendar year (complete years
    only), for the ``top`` partners of the latest year. Index year, one column per partner,
    largest first. The share is of the partners' total (``exclude`` rows left out)."""
    e = exports[(exports["product"] == product) & ~exports["partner"].isin(list(exclude))].copy()
    e["year"] = e["month"].astype(str).str[:4].astype(int)
    months = e.groupby("year")["month"].nunique()
    e = e[e["year"].isin(months[months == 12].index)]
    if e.empty:
        return pd.DataFrame()
    kg = e.groupby(["year", "partner"])["net_kg"].sum().unstack(fill_value=0.0)
    shares = kg.div(kg.sum(axis=1), axis=0)
    order = shares.iloc[-1].sort_values(ascending=False).index[:top]
    return shares[list(order)]


def share_shift_subtitle(shares: pd.DataFrame, what: str, n: int = 2) -> str:
    """"Italy's share of <what> went from 14% in 2000 to 29% in 2025; Germany's from ..."."""
    first, last = shares.index[0], shares.index[-1]
    parts = []
    for partner in shares.columns[:n]:
        a = round(float(shares.loc[first, partner]) * 100)
        b = round(float(shares.loc[last, partner]) * 100)
        if not parts:
            parts.append(f"{partner}'s share of {what} went from {a}% in {first} to {b}% in {last}")
        else:
            parts.append(f"{partner}'s from {a}% to {b}%")
    return "; ".join(parts) + "."


@dataclass(frozen=True)
class RatioStats:
    median: float
    q10: float
    q90: float
    n: int


def ratio_stats(a: pd.Series, b: pd.Series) -> RatioStats:
    """Median and 10th/90th percentiles of a / b (aligned on the index; gaps skipped)."""
    r = pd.Series(a, dtype=float) / pd.Series(b, dtype=float)
    r = r.replace([math.inf, -math.inf], math.nan).dropna()
    return RatioStats(float(r.median()), float(r.quantile(0.1)), float(r.quantile(0.9)), len(r))


def ratio_subtitle(stats: RatioStats, a_name: str, b_name: str) -> str:
    return (f"{a_name} sold for a median {stats.median:.2f} times {b_name} (8 in 10 months "
            f"between {stats.q10:.2f} and {stats.q90:.2f} times).")


# Exchanges

def gap_series(ref: pd.DataFrame, other: pd.DataFrame, col: str) -> pd.DataFrame:
    """``other`` / ``ref`` - 1 by month, for months where both have a ``col`` value."""
    m = ref[["month", col]].merge(other[["month", col]], on="month", suffixes=("_ref", "_oth"))
    m["gap"] = m[f"{col}_oth"] / m[f"{col}_ref"] - 1
    return m.dropna(subset=["gap"])[["month", "gap"]].reset_index(drop=True)


def _side(x: float) -> str:
    return f"{abs(x) * 100:.1f}% {'below' if x < 0 else 'above'}"


def gap_subtitle(gap: pd.DataFrame, name: str, ref_name: str) -> str:
    """"Ordu's monthly price ran a median 9.7% below Giresun's over 308 months; 8 in 10 ..."."""
    g = gap["gap"].dropna()
    med, lo, hi = float(g.median()), float(g.quantile(0.1)), float(g.quantile(0.9))
    if lo < 0 and hi < 0:
        band = f"between {abs(lo) * 100:.1f}% and {abs(hi) * 100:.1f}% below"
    elif lo >= 0 and hi >= 0:
        band = f"between {lo * 100:.1f}% and {hi * 100:.1f}% above"
    else:
        band = f"between {_side(lo)} and {_side(hi)}"
    return (f"{name}'s monthly price ran a median {_side(med)} {ref_name}'s over {len(g)} "
            f"months; 8 in 10 months fell {band}.")


def split_outliers(gap: pd.DataFrame, limit: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(months with |gap| <= ``limit``, months beyond it). The data is not changed; a page
    leaves the implausible months out and says so with ``outlier_note``."""
    far = gap["gap"].abs() > limit
    return gap[~far].reset_index(drop=True), gap[far].reset_index(drop=True)


def outlier_note(dropped: pd.DataFrame, name: str, ref_name: str, limit: float) -> str | None:
    if dropped.empty:
        return None
    months = _join_names([month_label(str(m)) for m in dropped["month"]])
    return (f"Left out: {months}, when {name}'s average was more than {round(limit * 100)}% "
            f"away from {ref_name}'s (most likely entry errors in the source).")


def gap_detail_subtitle(gap: pd.DataFrame, name: str) -> str:
    """How often ``name`` was dearer, and its widest discount (or premium, if never cheaper)."""
    g = gap.dropna(subset=["gap"])
    dearer = int((g["gap"] > 0).sum())
    lead = f"{name} was dearer in {dearer} of {len(g)} months"
    if (g["gap"] < 0).any():
        row = g.loc[g["gap"].idxmin()]
        return (f"{lead}; its widest discount was {abs(float(row['gap'])) * 100:.1f}%, "
                f"in {month_label(str(row['month']))}.")
    row = g.loc[g["gap"].idxmax()]
    return (f"{lead}; its widest premium was {float(row['gap']) * 100:.1f}%, "
            f"in {month_label(str(row['month']))}.")


# Crop and frost

def correlation_without_note(crop: pd.DataFrame, x_col: str, years: Sequence[int],
                             exclude_season: str | None = None) -> str | None:
    """The crop-size / season-price correlation with ``years`` left out (and the season
    in progress, if given), in words; None if too few seasons remain."""
    df = crop.dropna(subset=[x_col, "season_avg_usd"])
    if exclude_season is not None:
        df = df[df["season"] != exclude_season]
    df = df[~df["year"].isin(list(years))]
    if len(df) < MIN_SEASONS:
        return None
    r = float(df[x_col].corr(df["season_avg_usd"]))
    return (f"Without {_join_names([str(y) for y in years])}, the correlation is "
            f"{_r_text(r)} ({len(df)} seasons).")


def frost_words(r: float) -> str:
    """Plain words for a frost-days / crop-size correlation."""
    if r <= -0.4:
        return "more frost days have usually meant smaller crops"
    if r <= -0.2:
        return "more frost days have loosely gone with smaller crops"
    if r < 0.2:
        return "the frost-day count says little about the crop"
    return "more frost days have not meant smaller crops"


def frost_crop_subtitle(df: pd.DataFrame, frost_col: str, crop_col: str) -> str:
    d = df.dropna(subset=[frost_col, crop_col])
    if len(d) < MIN_SEASONS:
        return "Spring frost days against the crop estimate."
    r = float(d[frost_col].corr(d[crop_col]))
    return f"Over {len(d)} years, {frost_words(r)} (correlation {_r_text(r)})."


_COUNT_WORDS = {2: "two", 3: "three", 4: "four", 5: "five"}


def smallest_crops_note(df: pd.DataFrame, frost_col: str, crop_col: str, n: int = 2,
                        year_col: str = "year") -> str:
    """"The two smallest crops, 2004 and 2014, followed 8.7 and 2.3 frost days."."""
    d = df.dropna(subset=[frost_col, crop_col]).nsmallest(n, crop_col)
    years = _join_names([str(int(y)) for y in d[year_col]])
    days = _join_names([f"{v:.1f}" for v in d[frost_col]])
    if len(d) == 1:
        return f"The smallest crop, {years}, followed {days} frost days."
    return f"The {_COUNT_WORDS.get(len(d), len(d))} smallest crops, {years}, followed {days} frost days."


def partial_year_note(latest_year: int, built_at: str | None, last_month: int = 4) -> str | None:
    """A note when the data was built before ``latest_year``'s frost window (which ends
    with ``last_month``) was over, so that year's count is partial; else None."""
    if not built_at:
        return None
    try:
        built = datetime.fromisoformat(str(built_at))
    except ValueError:
        return None
    end = pd.Period(year=int(latest_year), month=last_month, freq="M").end_time
    if built.replace(tzinfo=None) > end:
        return None
    return (f"{latest_year} is partial: the data was built on {built.day} "
            f"{calendar.month_name[built.month]} {built.year}, before its frost window ended.")


# Tables

def fmt_ratio(dp: int):
    """A formatter for ratios with ``dp`` decimals."""
    return lambda x: NA if _missing(x) else f"{x:.{dp}f}"


def fmt_pct(x) -> str:
    """A fraction as a whole percent: ``0.8418`` -> ``84%``."""
    return NA if _missing(x) else f"{round(x * 100)}%"


def fmt_signed(x) -> str:
    """A signed number with two decimals: ``−0.10``, ``+0.18``; zero has no sign."""
    if _missing(x):
        return NA
    v = round(x, 2)
    return "0.00" if v == 0 else f"{'+' if v > 0 else MINUS}{abs(v):.2f}"


def fmt_p(x) -> str:
    """A p-value: two decimals, three when two would show 0.00, "<0.001" below that."""
    if _missing(x):
        return NA
    if x < 0.001:
        return "<0.001"
    return f"{x:.3f}" if round(x, 2) == 0 else f"{x:.2f}"


def metric_table_html(df: pd.DataFrame, groups, *, caption: str, row: str = "method",
                      col: str = "horizon", names=None, order: Sequence | None = None,
                      highlight: str | None = NAIVE, row_head: str = "Method",
                      col_label=None) -> str:
    """A table from a long frame: one row per ``row`` value, and for each group
    ``(label, value column, formatter)`` one column per ``col`` value (horizons by default,
    headed "1 mo"). With more than one group a spanning header names each group.

    ``names`` maps a row key to its label (falling back to ``method_name``); ``order``
    sets the row order (default: first appearance); the ``highlight`` row is amber."""
    cols = sorted(df[col].unique())
    keys = list(order) if order is not None else list(dict.fromkeys(df[row]))
    label = col_label or (lambda c: f"{c} mo")
    values = df.set_index([row, col])

    def name_of(k) -> str:
        return (names(k) if names else None) or method_name(str(k))

    head = ""
    if len(groups) > 1:
        head = "<tr><td></td>" + "".join(
            f'<th class="grp" scope="colgroup" colspan="{len(cols)}">{escape(g)}</th>'
            for g, _, _ in groups) + "</tr>"
    head += f'<tr><th scope="col">{escape(row_head)}</th>' + "".join(
        f'<th class="n" scope="col">{escape(label(c))}</th>' for _ in groups for c in cols
    ) + "</tr>"
    body = []
    for k in keys:
        cells = []
        for _, vcol, fmt in groups:
            for c in cols:
                v = values[vcol].get((k, c), math.nan)
                cells.append(f'<td class="n">{fmt(v)}</td>')
        cls = ' class="hl"' if highlight is not None and k == highlight else ""
        body.append(f"<tr{cls}><td>{escape(name_of(k))}</td>{''.join(cells)}</tr>")
    return (
        # Quarto restyles raw HTML tables (striped, visible caption) unless told not to.
        '<div class="table-wrap"><table class="metric" data-quarto-disable-processing="true">'
        f'<caption class="visually-hidden">{escape(caption)}</caption>'
        f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>"
    )


# Forecasting

def dev_subtitle(board: pd.DataFrame) -> str:
    """The development scoreboard's takeaway; names no method."""
    others = board[board["method"] != NAIVE]
    under = int((others["ratio"] < 1).sum())
    if under:
        return (f"{under} of {len(others)} method-horizon scores came in under 1 "
                "(below 1 beats naive), which could be chance.")
    closest = sorted(round((float(r) - 1) * 100)
                     for r in others.groupby("horizon")["ratio"].min())
    margin = (f"{closest[0]}%" if closest[0] == closest[-1]
              else f"{closest[0]}% to {closest[-1]}%")
    return f"None beat naive at any horizon; the closest lost by {margin}."


def shock_table(shocks: pd.DataFrame) -> pd.DataFrame:
    """``scoreboard_shocks.csv`` with one ratio column per period (method, horizon, calm, shock)."""
    wide = shocks.pivot_table(index=["method", "horizon"], columns="period", values="ratio")
    wide.columns.name = None
    return wide.reset_index()


def shock_multiple(shocks: pd.DataFrame, exclude: Sequence[str] = ()) -> tuple[float, float]:
    """The smallest and largest shock-month MAE / calm-month MAE over method-horizons,
    leaving out the methods in ``exclude``."""
    mae = shocks.pivot_table(index=["method", "horizon"], columns="period", values="mae")
    mult = mae["shock"] / mae["calm"]
    mult = mult[~mult.index.get_level_values("method").isin(list(exclude))]
    return float(mult.min()), float(mult.max())


def shock_subtitle(shocks: pd.DataFrame, exclude: Sequence[str] = ()) -> str:
    """How much bigger errors get in shock months (methods in ``exclude`` left out of that
    multiple), and how many shock-month scores came in under naive; names no method."""
    lo, hi = shock_multiple(shocks, exclude)
    lead = (f"In shock months the errors were {lo:.1f} to {hi:.1f} times "
            "their calm size, naive's included")
    sh = shocks[(shocks["period"] == "shock") & (shocks["method"] != NAIVE)]
    under = sh[sh["ratio"] < 1]
    if under.empty:
        return f"{lead}; no method beat naive there."
    best = round((1 - float(under["ratio"].min())) * 100)
    return (f"{lead}; {len(under)} of {len(sh)} shock-month scores came in under 1, "
            f"by at most {best}%.")


def holdout_subtitle(holdout: pd.DataFrame) -> str:
    """The holdout's takeaway, labelled as scored once. Names a method only if it came in
    under naive at every horizon, and then says that could be chance."""
    n = count_text(holdout["n"])
    lead = f"{n} forecasts per horizon, {HOLDOUT_NOTE}."
    rows = [(m, name, r) for m, name, r in scoreboard_rows(holdout) if m != NAIVE]
    winners = [name for _, name, r in rows if r and all(v < 1 for v in r.values())]
    if winners:
        return (f"{lead} {_join_names(winners)} came in under naive at every horizon; on "
                f"{n} forecasts per horizon that could be chance (no significance test was "
                "run on the holdout).")
    others = holdout[holdout["method"] != NAIVE]
    under = others[others["ratio"] < 1]
    if under.empty:
        return f"{lead} No method beat naive at any horizon."
    lost = all(any(v > 1 for v in r.values()) for m, _, r in rows if m in set(under["method"]))
    tail = ", each from a method that lost at another horizon" if lost else ""
    return (f"{lead} No method beat naive at every horizon; {len(under)} of {len(others)} "
            f"scores came in under 1{tail}.")


def holdout_dev_note(holdout: pd.DataFrame, dev: pd.DataFrame) -> str | None:
    """Whether the holdout's scores under 1 were also under 1 in development."""
    under = holdout[(holdout["method"] != NAIVE) & (holdout["ratio"] < 1)]
    if under.empty:
        return None
    d = dev.set_index(["method", "horizon"])["ratio"]
    both = sum(1 for m, h in zip(under["method"], under["horizon"])
               if (m, h) in d.index and float(d[(m, h)]) < 1)
    if both == 0:
        return "None of the holdout scores under 1 was under 1 in development at the same horizon."
    verb = "was" if both == 1 else "were"
    return (f"{both} of the holdout scores under 1 {verb} also under 1 in development at the "
            "same horizon.")


def forecast_3m_subtitle(f: pd.DataFrame, horizon: int) -> str:
    """Naive's mean miss on ``forecast_3m.csv`` and how the closest challenger compares."""
    naive = float((f["naive"] - f["actual"]).abs().mean())
    other = float((f["best_other"] - f["actual"]).abs().mean())
    pct = round((other / naive - 1) * 100)
    name = method_name(str(f["best_other_method"].iloc[0]))
    return (f"{horizon} months ahead, naive missed by {fmt_usd(naive)}/kg on average; {name}, "
            f"the closest challenger, missed by {abs(pct)}% {'more' if pct >= 0 else 'less'}.")


def _in_periods(month: str, periods: Sequence[tuple[str, str]]) -> bool:
    return any(a <= month <= b for a, b in periods)


def _band_rows(band: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    b = band.dropna(subset=["actual", "q10", "q90"])
    return b, (b["q10"] <= b["actual"]) & (b["actual"] <= b["q90"])


def band_held(band: pd.DataFrame) -> tuple[float, int, int]:
    """(share held, months held, months) for an 8-in-10 band; the edges count as held, as
    in the backtest's coverage score."""
    b, held = _band_rows(band)
    return float(held.mean()), int(held.sum()), len(b)


def band_subtitle(band: pd.DataFrame, shocks: Sequence[tuple[str, str]], horizon: int) -> str:
    """How often the 8-in-10 range (q10..q90, edges count as held) held, and how many of its
    misses fell in a shock period."""
    b, held = _band_rows(band)
    share, n_held, n = band_held(band)
    shock = b["target_month"].astype(str).map(lambda m: _in_periods(m, shocks))
    misses = n - n_held
    lead = (f"{horizon} months ahead, the 8-in-10 range held {fmt_pct(share)} of the "
            f"time ({n_held} of {n} months)")
    if misses == 0:
        return f"{lead}."
    return f"{lead}; {int((~held & shock).sum())} of the {misses} misses fell in a shock period."


def crop_check_table(dev: pd.DataFrame, check: pd.DataFrame, main_source: str) -> pd.DataFrame:
    """Rows for the crop-estimate check: per method, the ``main_source`` estimate on time
    (``dev``), then each source's estimate a month late (``check``). Columns row, horizon,
    ratio."""
    rows = []
    for m in dict.fromkeys(check["method"]):
        name = method_name(str(m))
        d = dev[dev["method"] == m]
        rows += [(f"{name}, {main_source.capitalize()}, on time", int(h), float(r))
                 for h, r in zip(d["horizon"], d["ratio"])]
        for src in dict.fromkeys(check["crop_source"]):
            c = check[(check["method"] == m) & (check["crop_source"] == src)]
            rows += [(f"{name}, {str(src).capitalize()}, a month late", int(h), float(r))
                     for h, r in zip(c["horizon"], c["ratio"])]
    return pd.DataFrame(rows, columns=["row", "horizon", "ratio"])


def crop_check_subtitle(dev: pd.DataFrame, check: pd.DataFrame, main_source: str) -> str:
    """How far the scores moved with every crop estimate a month late, and how the other
    estimate(s) compared with ``main_source`` on the same late timing."""
    on_time = dev.set_index(["method", "horizon"])["ratio"]
    late = check[check["crop_source"] == main_source].set_index(["method", "horizon"])["ratio"]
    common = late.index.intersection(on_time.index)
    shift = float((late[common] - on_time[common]).abs().max())
    others = check[check["crop_source"] != main_source]
    cmp = others.set_index(["method", "horizon"]).join(late.rename("main"), how="inner")
    worse = int((cmp["ratio"] > cmp["main"]).sum())
    sources = _join_names(list(dict.fromkeys(others["crop_source"].astype(str))))
    under = int((check["ratio"] < 1).sum())
    tail = ("and nothing beat naive" if under == 0
            else f"and {under} of {len(check)} scores came in under naive")
    return (f"Making every crop estimate a month later changed the scores by at most "
            f"{shift:.2f}; the {sources} estimate scored worse in {worse} of {len(cmp)} "
            f"method-horizon pairs, {tail}.")


def lira_split(lira: pd.DataFrame, method: str, periods: Sequence[str]) -> pd.DataFrame:
    """``method``'s MAPE ratio by horizon (index) and period (columns, in ``periods`` order)."""
    r = lira[(lira["method"] == method) & lira["period"].isin(list(periods))]
    wide = r.pivot_table(index="horizon", columns="period", values="mape_ratio")
    return wide[list(periods)].rename_axis(columns=None)


def _vs_naive(values) -> str:
    pcts = sorted(round((float(v) - 1) * 100) for v in values)
    lo, hi = pcts[0], pcts[-1]
    if hi < 0:
        return f"{-hi}% below naive's" if lo == hi else f"{-hi}% to {-lo}% below naive's"
    if lo > 0:
        return f"{lo}% above naive's" if lo == hi else f"{lo}% to {hi}% above naive's"
    return f"between {-lo}% below and {hi}% above naive's"


def lira_split_subtitle(lira: pd.DataFrame, method: str, calm: str = "calm",
                        crisis: str = "crisis") -> str:
    w = lira_split(lira, method, (calm, crisis))
    within = round(float((w[calm] - 1).abs().max()) * 100)
    return (f"In the {crisis} months its error was {_vs_naive(w[crisis])}; in {calm} months "
            f"it was within {within}% of naive's.")


def lira_p_note(lira: pd.DataFrame, methods: Mapping[str, str]) -> str:
    """Diebold-Mariano p-values over all months (the calm / crisis ones are approximate)."""
    a = lira[lira["period"] == "all"]
    parts = []
    for code, name in methods.items():
        r = a[a["method"] == code].sort_values("horizon")
        ps = " / ".join(fmt_p(p) for p in r["dm_p"])
        hs = " / ".join(str(int(h)) for h in r["horizon"])
        parts.append(f"{name}: p = {ps} at {hs} months")
    return "; ".join(parts) + "."


def periods_label(periods: Sequence[tuple[str, str]]) -> str:
    """[("2018-05", "2018-12"), ("2021-09", "2023-12")] ->
    "May to December 2018 and September 2021 to December 2023"."""
    def one(a: str, b: str) -> str:
        if a[:4] == b[:4]:
            return f"{calendar.month_name[int(a[5:])]} to {month_label(b)}"
        return f"{month_label(a)} to {month_label(b)}"
    return _join_names([one(a, b) for a, b in periods])


def ranges_order(ranges: pd.DataFrame, base: str) -> list[str]:
    """Range methods for the table: ``base`` first, then by mean skill, best first."""
    skill = ranges.groupby("method")["skill"].mean()
    rest = skill.drop(base, errors="ignore").sort_values(ascending=False)
    return ([base] if base in skill.index else []) + list(rest.index)


def ranges_subtitle(ranges: pd.DataFrame, base: str) -> str:
    """How often ``base``'s 8-in-10 range held, and whether any method's skill beat it."""
    b = ranges[ranges["method"] == base]
    covs = sorted(round(float(c) * 100) for c in b["cov80"])
    lo, hi = covs[0], covs[-1]
    held = f"{lo}%" if lo == hi else f"{lo}% to {hi}%"
    others = ranges[ranges["method"] != base]
    better = int((others["skill"] > 0).sum())
    tail = ("no other method scored better at any horizon" if better == 0
            else f"{better} of {len(others)} other scores beat it")
    return (f"An honest 8-in-10 range holds about 80% of the time. {method_name(base)} held "
            f"{held}, and {tail}.")


def lira_subtitle(lira: pd.DataFrame, trend: Sequence[str], trend_words: str) -> str:
    """The lira table's takeaway over all months: the first horizon, then the gains of the
    ``trend`` methods at the longer horizons (MAPE ratio vs naive)."""
    a = lira[(lira["period"] == "all") & (lira["method"] != NAIVE)]
    h1 = int(a["horizon"].min())
    first = a[a["horizon"] == h1]
    beat = int((first["mape_ratio"] < 1).sum())
    lead = (f"In percent terms nothing beat naive at {_plural(h1, 'month')}" if beat == 0
            else f"In percent terms {beat} of {len(first)} methods beat naive at "
                 f"{_plural(h1, 'month')}")
    rest = a[a["method"].isin(list(trend)) & (a["horizon"] > h1)]
    if rest.empty:
        return f"{lead}."
    hs = _join_names([str(int(h)) for h in sorted(rest["horizon"].unique())])
    gains = sorted(round((1 - float(r)) * 100) for r in rest["mape_ratio"])
    lo, hi = gains[0], gains[-1]
    if lo > 0:
        size = f"{lo}% lower" if lo == hi else f"{lo}% to {hi}% lower"
    else:
        size = f"between {-lo}% higher and {hi}% lower" if hi > 0 else f"{-hi}% to {-lo}% higher"
    return f"{lead}; at {hs} months {trend_words} had {size} error."

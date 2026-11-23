"""Number formats, small HTML fragments and computed takeaways for the site's pages
(home, overview, dashboard, analyses).

Pages call these from Python cells and emit the HTML as a raw block (see ``raw_html``).
Nothing here assumes a crop or a country: the page passes in its labels. Every word comes
from ``site/i18n/{en,tr}.yml`` through ``hazelnut.site.i18n``, in the active language.
"""
from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Mapping

import pandas as pd

from hazelnut.site import i18n
from hazelnut.site.config import CropConfig, LocalCurrency
from hazelnut.site.i18n import MINUS, join_names, month_label, month_name, plural, t
from hazelnut.site.labels import (OTHER_PARTNER, METHOD_ANCHORS, crop_estimate_label,
                                  method_name, scroll_hint)

ARROW = '<svg class="ico" aria-hidden="true"><use href="#arrow-right"/></svg>'


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def na() -> str:
    """The text for a missing value: ``n/a``."""
    return t("na")


def fmt_usd(x) -> str:
    """US dollars with two decimals: ``$4.28``."""
    return i18n.fmt_usd(x)


def fmt_number(x) -> str:
    """A price in another currency, two decimals: ``208.15`` (the page adds the unit)."""
    return i18n.fmt_number(x)


def fmt_change(x) -> str:
    """A fractional change as a signed percent with one decimal: ``−5.3%``, ``+31.5%``."""
    return i18n.fmt_pct(x, 1, signed=True)


def fmt_tonnes(x) -> str:
    """Tonnes with thousands separators: ``86,440``."""
    return i18n.fmt_tonnes(x)


def _parse(as_of: str) -> tuple[int, int | None]:
    """``"2026-09"`` -> (2026, 9); a yearly ``"2026"`` -> (2026, None)."""
    year, _, month = str(as_of).partition("-")
    return int(year), (int(month) if month else None)


def previous_month_name(as_of: str) -> str:
    """The month before ``as_of`` by name: ``"2026-01"`` -> ``"December"``."""
    _, month = _parse(as_of)
    return month_name(12 if month == 1 else month - 1)


def as_of_stamp(manifest: Mapping) -> str:
    """"Data as of <Month YYYY> · refreshed weekly", plus the oldest stale source if any.

    A stale output with no date (it failed and had no earlier file) is "unavailable".
    """
    return i18n.as_of(manifest)


def output_month_label(manifest: Mapping | None, name: str) -> str | None:
    """The readable "as of" of one output in the manifest, or None if it has no date."""
    entry = (manifest or {}).get("outputs", {}).get(name) or {}
    return month_label(entry["as_of"]) if entry.get("as_of") else None


def market_meta_html(manifest: Mapping) -> str:
    """The row above the stat strip: "The market this month" and the as-of stamp."""
    return (
        f'<div class="meta"><span class="eyebrow">{escape(t("overview.market_eyebrow"))}</span>'
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


def market_strip_html(stats: Mapping, *, local_name: str, local: LocalCurrency, crop_source: str) -> str:
    """The four-stat "market this month" strip.

    ``local_name`` names the local currency in the label ("Price, lira"), ``local`` is the
    crop's local currency (its label is the unit, "TL" -> "TL/kg", and its column names the
    stats keys), ``crop_source`` says whose crop estimate it is (named in the tile label).
    """
    prev = escape(previous_month_name(stats["as_of"]))
    missing = na()

    if _missing(stats.get("from_peak")) or _missing(stats.get("peak_usd")) or not stats.get("peak_month"):
        peak_sub = escape(t("strip.peak_na"))
    else:
        peak_sub = escape(t("strip.since_peak", month=month_label(stats["peak_month"]),
                            price=fmt_usd(stats["peak_usd"])))

    year = stats.get("crop_year")
    estimate = stats.get("crop_estimate_t")
    if _missing(estimate):
        crop_value, crop_sub = missing, escape(t("strip.no_estimate"))
    else:
        crop_value = f"{fmt_tonnes(estimate)}<small> {escape(t('unit.tonnes'))}</small>"
        if _missing(stats.get("crop_yoy")) or _missing(year):
            crop_sub = escape(t("strip.no_earlier_year"))
        else:
            crop_sub = t("strip.change_on_year", change=_change_span(stats["crop_yoy"]),
                         year=int(year) - 1)
    crop_label = escape(crop_estimate_label(crop_source, None if _missing(year) else int(year)))

    usd = fmt_usd(stats.get("usd_kg"))
    local_price = fmt_number(stats.get(local.column))
    per_kg = escape(t("unit.per_kg"))
    local_per_kg = escape(t("unit.local_per_kg", unit=local.label))
    stats_html = [
        _stat(escape(t("strip.price_usd")),
              usd + ("" if usd == missing else f"<small> {per_kg}</small>"),
              t("strip.change_on_month", change=_change_span(stats.get("usd_mom")), month=prev)),
        _stat(escape(t("strip.price_local", name=local_name)),
              local_price + ("" if local_price == missing else f"<small> {local_per_kg}</small>"),
              t("strip.change_on_month", change=_change_span(stats.get(local.mom_key)), month=prev)),
        _stat(escape(t("strip.from_peak")), fmt_change(stats.get("from_peak")), peak_sub),
        _stat(crop_label, crop_value, crop_sub),
    ]
    return '<div class="strip">' + "".join(stats_html) + "</div>"


def exchanges_phrase(exchanges) -> str:
    """("Giresun", "Ordu") -> "Giresun & Ordu exchanges"."""
    names = list(exchanges)
    if len(names) == 1:
        return t("exchanges.one", name=names[0])
    return t("exchanges.many", names=", ".join(names[:-1]), last=names[-1])


def sources_summary(sources) -> tuple[str, str]:
    """("8 public datasets", "Giresun & Ordu exchanges, UN Comtrade, ...") from a crop's
    ``WORKBOOK_SOURCES`` rows (provider name first). Commodity exchanges (names ending in
    the language's "Commodity Exchange") are grouped."""
    suffix = t("sources.exchange_suffix")
    names = [row[0] for row in sources]
    cities = [n.removesuffix(suffix) for n in names if n.endswith(suffix)]
    others = [n for n in names if not n.endswith(suffix)]
    listed = ([exchanges_phrase(cities)] if cities else []) + others
    return plural("sources.count", len(names)), ", ".join(listed)


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
                text = t("home.crop_price", price=fmt_usd(stats["usd_kg"]),
                         month=month_label(stats["as_of"]))
                price = f"<p>{escape(text, quote=False)}</p>"
        where = escape(t("home.crop_where", country=i18n.crop_country(crop),
                         exchanges=exchanges_phrase(crop.exchanges)))
        cards.append(
            f'<a class="panel crop-card" href="{escape(crop.slug)}/index.qmd">'
            f'<span class="eyebrow">{where}</span>'
            f"<h3>{escape(i18n.crop_name(crop))} {ARROW}</h3>{price}</a>"
        )
    return '<div class="crops">' + "".join(cards) + "</div>"


def raw_html(html: str) -> None:
    """Display ``html`` in a Quarto page as a raw HTML block (no text/html output, see
    ``charts.show``)."""
    import IPython.display

    IPython.display.display(IPython.display.Markdown("```{=html}\n" + html + "\n```\n"))


# --- Dashboard --------------------------------------------------------------------------
# Panel loading with an error state, and each panel's takeaway, computed from the data.

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
    return f'<div class="chart-error" role="note">{escape(t("panel.unavailable"), quote=False)}</div>'


def panel_head_html(title: str, sub: str) -> str:
    """A dashboard panel's title and its one-line takeaway."""
    return (f'<h2 class="ptitle">{escape(title, quote=False)}</h2>'
            f'<div class="sub">{escape(sub, quote=False)}</div>')


def _months(n: int) -> str:
    """"1 month", "14 months"."""
    return plural("unit.months", n)


def _join_names(names: Sequence[str]) -> str:
    return join_names(names)


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
        key = "price.shock_next" if parts else "price.shock_first"
        parts.append(t(key, name=name, low=fmt_usd(m.low), peak=fmt_usd(m.peak),
                       span=_months(m.months)))
    if not parts:
        return t("price.fallback")
    return i18n.upper_first("; ".join(parts) + ".")


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
    return t("range.subtitle", horizon=int(row["horizon"]),
             month=month_label(str(row["target_month"])),
             low=fmt_usd(float(row["q10"])), high=fmt_usd(float(row["q90"])))


def range_coverage_note(ranges: pd.DataFrame | None, method: str, horizon: int) -> str | None:
    """How often the 8-in-10 band held in the backtest (``results/ranges.csv``), or None."""
    if ranges is None or not {"method", "horizon", "cov80"} <= set(ranges.columns):
        return None
    hit = ranges[(ranges["method"] == method) & (ranges["horizon"] == horizon)]
    if hit.empty or _missing(float(hit["cov80"].iloc[0])):
        return None
    return t("range.coverage_note", pct=fmt_pct(float(hit["cov80"].iloc[0])),
             span=_months(horizon))


def range_currencies_label(currencies: Sequence[str]) -> str:
    """crops.yml ``range_currencies`` as shown on the page: ("usd",) -> "USD"."""
    return ", ".join(c.upper() for c in currencies)


def exports_subtitle(top: pd.DataFrame, period_end: str, n: int = 2) -> str:
    """"Italy and Germany took 51% of export volume in the 12 months to December 2025."
    The "Other" bucket is never named as a destination."""
    named = top[top["partner"] != OTHER_PARTNER].sort_values("share", ascending=False).head(n)
    return t("exports.subtitle",
             names=_join_names([i18n.country_name(p) for p in named["partner"].astype(str)]),
             share=fmt_pct(float(named["share"].sum())), period=period_end)


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
        span = t("span.only", month=month_label(first))
    elif first[:4] == last[:4]:
        span = t("span.same_year", first=month_name(int(first[5:])), last=month_label(last))
    else:
        span = t("span.years", first=month_label(first), last=month_label(last))
    return t("season.to_date_note", season=season, span=span)


def _strength(r: float) -> str:
    """The key of a correlation's plain-words variant."""
    if r <= -0.4:
        return "strong_negative"
    if r <= -0.2:
        return "weak_negative"
    if r < 0.2:
        return "none"
    return "positive"


def correlation_words(r: float) -> str:
    """Plain words for a crop-size / price correlation."""
    return t(f"crop_price.words.{_strength(r)}")


MIN_SEASONS = 3


def crop_price_subtitle(crop: pd.DataFrame, x_col: str, exclude_season: str | None = None) -> str:
    """The crop-size / season-price link over complete seasons, in words with the r."""
    df = crop.dropna(subset=[x_col, "season_avg_usd"])
    if exclude_season is not None:
        df = df[df["season"] != exclude_season]
    if len(df) < MIN_SEASONS:
        return t("crop_price.fallback")
    r = float(df[x_col].corr(df["season_avg_usd"]))
    return t(f"crop_price.subtitle.{_strength(r)}", n=len(df), r=_r_text(r))


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
        df.loc[df["season"] == partial, "season"] = t("season.to_date_label", season=partial)
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
    if under == 0:
        return t("scoreboard.subtitle_none")
    return t("scoreboard.subtitle_some", under=under, total=len(others))


def _holdout_sentence(holdout: pd.DataFrame) -> str:
    under = [name for m, name, r in scoreboard_rows(holdout)
             if m != NAIVE and r and all(v < 1 for v in r.values())]
    if under:
        return t("scoreboard.holdout_winners", names=_join_names(under))
    return t("scoreboard.holdout_none")


def method_cell(method: str, name: str, methods_href: str | None) -> str:
    """A method's table label, linked to its Methods page card when ``methods_href`` (the
    relative path of methods.qmd) is given and the method has one."""
    anchor = METHOD_ANCHORS.get(method)
    if methods_href is None or anchor is None:
        return escape(name)
    return f'<a href="{escape(methods_href)}#{anchor}">{escape(name)}</a>'


def scoreboard_html(dev: pd.DataFrame, holdout: pd.DataFrame | None, analysis_href: str,
                    methods_href: str | None = None) -> str:
    """The dev scoreboard as a table (naive row in amber) and its footnote. With
    ``methods_href`` each method name links to its Methods page card."""
    horizons = sorted(int(h) for h in dev["horizon"].unique())
    head = "".join(f'<th class="n" scope="col">{escape(t("unit.mo", n=h))}</th>' for h in horizons)
    body = []
    for m, name, r in scoreboard_rows(dev):
        cls = ' class="hl"' if m == NAIVE else ""
        cells = "".join(f'<td class="n">{fmt_ratio(2)(r[h])}</td>' if h in r
                        else f'<td class="n">{escape(na())}</td>' for h in horizons)
        body.append(f"<tr{cls}><td>{method_cell(m, name, methods_href)}</td>{cells}</tr>")
    foot = escape(t("scoreboard.foot", count=count_text(dev["n"])), quote=False)
    if holdout is not None and not holdout.empty:
        foot += " " + escape(_holdout_sentence(holdout), quote=False)
    foot += (f' <a href="{escape(analysis_href)}">'
             f'{escape(t("scoreboard.analysis_link"), quote=False)}</a>')
    return (
        # Quarto restyles raw HTML tables (striped, visible caption) unless told not to.
        '<table class="scoreboard" data-quarto-disable-processing="true">'
        f'<caption class="visually-hidden">{escape(t("scoreboard.caption"))}'
        "</caption>"
        f'<thead><tr><th scope="col">{escape(t("table.method"))}</th>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table>"
        f'<p class="foot">{foot}</p>'
    )


# --- Analyses ---------------------------------------------------------------------------
# The analyses pages: index cards, page head, and each panel's takeaway or table, computed
# from the site data. Labels (crop, exchange and method names) come from the page.

def _r_text(r: float) -> str:
    """A correlation with two decimals and a real minus sign: ``−0.45``, ``0.12``."""
    return i18n.fmt_number(r, 2).replace("-", MINUS)


def _span(lo: str, hi: str) -> str:
    """``lo`` alone when it equals ``hi``, else "lo to hi"."""
    return lo if lo == hi else t("span.values", low=lo, high=hi)


def _pct_points(n: int) -> str:
    """A whole number of percent points as a percent: ``12`` -> ``12%``."""
    return fmt_pct(n / 100)


def count_text(n: pd.Series) -> str:
    lo, hi = int(n.min()), int(n.max())
    return _span(str(lo), str(hi))


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
    return (f'<nav class="analyses" aria-label="{escape(t("analyses.nav_label"))}">'
            + "".join(cards) + "</nav>")


def analysis_head_html(crop_name: str, page: str, h1: str, found: str,
                       stamp: str | None = None) -> str:
    """An analysis page's head: eyebrow (with a link back to the analyses list), h1, the
    optional as-of stamp, and the "What we found" paragraph."""
    live = (f'<span class="live"><i aria-hidden="true"></i>{escape(stamp, quote=False)}</span>'
            if stamp else "")
    analyses = f'<a href="index.qmd">{escape(t("analyses.nav_label"))}</a>'
    eyebrow = t("analyses.eyebrow", crop=escape(crop_name), analyses=analyses, page=escape(page))
    return (
        '<div class="dash-head"><div>'
        f'<span class="eyebrow">{eyebrow}</span>'
        f"<h1>{escape(h1, quote=False)}</h1></div>{live}</div>"
        f'<div class="found"><span class="eyebrow">{escape(t("analyses.found"))}</span>'
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
    out["label"] = out["month"].map(month_name)
    return out.reset_index(drop=True)[cols]


def seasonality_subtitle(profile: pd.DataFrame) -> str:
    """The lowest and highest month on average, and how wide seasons spread around it."""
    lo = profile.loc[profile["mean"].idxmin()]
    hi = profile.loc[profile["mean"].idxmax()]
    spread = round(float((profile["q75"] - profile["q25"]).median()) * 100)
    return t("seasonality.subtitle", seasons=int(profile["seasons"].max()),
             low=fmt_change(lo["mean"]), low_month=lo["label"],
             high=fmt_change(hi["mean"]), high_month=hi["label"], spread=spread)


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
        a = fmt_pct(float(shares.loc[first, partner]))
        b = fmt_pct(float(shares.loc[last, partner]))
        if not parts:
            parts.append(t("exports.share_first", partner=i18n.country_name(partner), what=what,
                           first_share=a,
                           first=first, last_share=b, last=last))
        else:
            parts.append(t("exports.share_next", partner=i18n.country_name(partner),
                           first_share=a, last_share=b))
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
    num = i18n.fmt_number
    return t("exports.ratio_subtitle", a=a_name, b=b_name, median=num(stats.median),
             low=num(stats.q10), high=num(stats.q90))


# Exchanges

def gap_series(ref: pd.DataFrame, other: pd.DataFrame, col: str) -> pd.DataFrame:
    """``other`` / ``ref`` - 1 by month, for months where both have a ``col`` value."""
    m = ref[["month", col]].merge(other[["month", col]], on="month", suffixes=("_ref", "_oth"))
    m["gap"] = m[f"{col}_oth"] / m[f"{col}_ref"] - 1
    return m.dropna(subset=["gap"])[["month", "gap"]].reset_index(drop=True)


def _gap_pct(x: float) -> str:
    """The size of a gap (its sign is said in words): ``9.7%``."""
    return i18n.fmt_pct(abs(x), 1)


def gap_subtitle(gap: pd.DataFrame, name: str, ref_name: str) -> str:
    """"Ordu's monthly price ran a median 9.7% below Giresun's over 308 months; 8 in 10 ..."."""
    g = gap["gap"].dropna()
    med, lo, hi = float(g.median()), float(g.quantile(0.1)), float(g.quantile(0.9))
    median = t("gap.median_below" if med < 0 else "gap.median_above", name=name,
               pct=_gap_pct(med), ref=ref_name, n=len(g))
    if lo < 0 and hi < 0:  # smallest discount first
        band = t("gap.band_below", low=_gap_pct(hi), high=_gap_pct(lo))
    elif lo >= 0 and hi >= 0:
        band = t("gap.band_above", low=_gap_pct(lo), high=_gap_pct(hi))
    else:  # lo below, hi above
        band = t("gap.band_mixed", low=_gap_pct(lo), high=_gap_pct(hi))
    return f"{median}; {band}."


def split_outliers(gap: pd.DataFrame, limit: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(months with |gap| <= ``limit``, months beyond it). The data is not changed; a page
    leaves the implausible months out and says so with ``outlier_note``."""
    far = gap["gap"].abs() > limit
    return gap[~far].reset_index(drop=True), gap[far].reset_index(drop=True)


def outlier_note(dropped: pd.DataFrame, name: str, ref_name: str, limit: float) -> str | None:
    if dropped.empty:
        return None
    months = _join_names([month_label(str(m)) for m in dropped["month"]])
    return t("gap.outlier_note", months=months, name=name, limit=fmt_pct(limit), ref=ref_name)


def gap_detail_subtitle(gap: pd.DataFrame, name: str) -> str:
    """How often ``name`` was dearer, and its widest discount (or premium, if never cheaper)."""
    g = gap.dropna(subset=["gap"])
    dearer = int((g["gap"] > 0).sum())
    if (g["gap"] < 0).any():
        row, key = g.loc[g["gap"].idxmin()], "gap.detail_discount"
    else:
        row, key = g.loc[g["gap"].idxmax()], "gap.detail_premium"
    return t(key, name=name, dearer=dearer, n=len(g), pct=_gap_pct(float(row["gap"])),
             month=month_label(str(row["month"])))


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
    return t("frost.without_note", years=_join_names([str(y) for y in years]), r=_r_text(r),
             n=len(df))


def frost_words(r: float) -> str:
    """Plain words for a frost-days / crop-size correlation."""
    return t(f"frost.words.{_strength(r)}")


def frost_crop_subtitle(df: pd.DataFrame, frost_col: str, crop_col: str,
                        crop_source: str | None = None) -> str:
    d = df.dropna(subset=[frost_col, crop_col])
    if len(d) < MIN_SEASONS:
        if crop_source:
            return t("frost.fallback", source=crop_source)
        return t("frost.fallback_no_source")
    r = float(d[frost_col].corr(d[crop_col]))
    return t(f"frost.subtitle.{_strength(r)}", n=len(d), r=_r_text(r))


def _count_word(n: int) -> str:
    """``2`` -> "two" (up to five), else the number."""
    key = f"count_word.{n}"
    return t(key) if i18n.has(key) else str(n)


def smallest_crops_note(df: pd.DataFrame, frost_col: str, crop_col: str, n: int = 2,
                        year_col: str = "year") -> str:
    """"The two smallest crops, 2004 and 2014, followed 8.7 and 2.3 frost days."."""
    d = df.dropna(subset=[frost_col, crop_col]).nsmallest(n, crop_col)
    years = _join_names([str(int(y)) for y in d[year_col]])
    days = _join_names([i18n.fmt_number(v, 1) for v in d[frost_col]])
    if len(d) == 1:
        return t("frost.smallest_one", years=years, days=days)
    return t("frost.smallest_many", count=_count_word(len(d)), years=years, days=days)


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
    date = t("format.day_month_year", day=built.day, month=month_name(built.month),
             year=built.year)
    return t("frost.partial_year", year=latest_year, date=date)


# Tables

def fmt_ratio(dp: int):
    """A formatter for ratios with ``dp`` decimals."""
    return lambda x: i18n.fmt_number(x, dp)


def fmt_pct(x) -> str:
    """A fraction as a whole percent: ``0.8418`` -> ``84%``."""
    return i18n.fmt_pct(x)


def fmt_signed(x) -> str:
    """A signed number with two decimals: ``−0.10``, ``+0.18``; zero has no sign."""
    return i18n.fmt_signed(x)


def fmt_p(x) -> str:
    """A p-value: two decimals, three when two would show 0.00, "<0.001" below that."""
    if _missing(x):
        return na()
    if x < 0.001:
        return "<" + i18n.fmt_number(0.001, 3)
    return i18n.fmt_number(x, 3 if round(x, 2) == 0 else 2)


def metric_table_html(df: pd.DataFrame, groups, *, caption: str, row: str = "method",
                      col: str = "horizon", names=None, order: Sequence | None = None,
                      highlight: str | None = NAIVE, row_head: str | None = None,
                      col_label=None, methods_href: str | None = None) -> str:
    """A table from a long frame: one row per ``row`` value, and for each group
    ``(label, value column, formatter)`` one column per ``col`` value (horizons by default,
    headed "1 mo"). With more than one group a spanning header names each group.
    ``row_head`` heads the name column (default "Method").

    ``names`` maps a row key to its label (falling back to ``method_name``); ``order``
    sets the row order (default: first appearance); the ``highlight`` row is amber. With
    ``methods_href`` (rows that are methods) each name links to its Methods page card."""
    cols = sorted(df[col].unique())
    keys = list(order) if order is not None else list(dict.fromkeys(df[row]))
    label = col_label or (lambda c: t("unit.mo", n=c))
    row_head = t("table.method") if row_head is None else row_head
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
        body.append(f"<tr{cls}><td>{method_cell(str(k), name_of(k), methods_href)}</td>{''.join(cells)}</tr>")
    return (
        # Quarto restyles raw HTML tables (striped, visible caption) unless told not to.
        f'<div class="table-wrap" data-scroll-hint="{escape(scroll_hint())}">'
        '<table class="metric" data-quarto-disable-processing="true">'
        f'<caption class="visually-hidden">{escape(caption)}</caption>'
        f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>"
    )


# Forecasting

def dev_subtitle(board: pd.DataFrame) -> str:
    """The development scoreboard's takeaway; names no method."""
    others = board[board["method"] != NAIVE]
    under = int((others["ratio"] < 1).sum())
    if under:
        return t("forecast.dev_some", under=under, total=len(others))
    closest = sorted(round((float(r) - 1) * 100)
                     for r in others.groupby("horizon")["ratio"].min())
    margin = _span(_pct_points(closest[0]), _pct_points(closest[-1]))
    return t("forecast.dev_none", margin=margin)


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
    lo, hi = (i18n.fmt_number(v, 1) for v in shock_multiple(shocks, exclude))
    sh = shocks[(shocks["period"] == "shock") & (shocks["method"] != NAIVE)]
    under = sh[sh["ratio"] < 1]
    if under.empty:
        return t("forecast.shock_none", low=lo, high=hi)
    best = round((1 - float(under["ratio"].min())) * 100)
    return t("forecast.shock_some", low=lo, high=hi, under=len(under), total=len(sh),
             best=_pct_points(best))


def holdout_subtitle(holdout: pd.DataFrame) -> str:
    """The holdout's takeaway, labelled as scored once. Names a method only if it came in
    under naive at every horizon, and then says that could be chance."""
    n = count_text(holdout["n"])
    rows = [(m, name, r) for m, name, r in scoreboard_rows(holdout) if m != NAIVE]
    winners = [name for _, name, r in rows if r and all(v < 1 for v in r.values())]
    if winners:
        return t("forecast.holdout_winners", n=n, names=_join_names(winners))
    others = holdout[holdout["method"] != NAIVE]
    under = others[others["ratio"] < 1]
    if under.empty:
        return t("forecast.holdout_none", n=n)
    lost = all(any(v > 1 for v in r.values()) for m, _, r in rows if m in set(under["method"]))
    return t("forecast.holdout_some_lost" if lost else "forecast.holdout_some", n=n,
             under=len(under), total=len(others))


def holdout_dev_note(holdout: pd.DataFrame, dev: pd.DataFrame) -> str | None:
    """Whether the holdout's scores under 1 were also under 1 in development."""
    under = holdout[(holdout["method"] != NAIVE) & (holdout["ratio"] < 1)]
    if under.empty:
        return None
    d = dev.set_index(["method", "horizon"])["ratio"]
    both = sum(1 for m, h in zip(under["method"], under["horizon"])
               if (m, h) in d.index and float(d[(m, h)]) < 1)
    lost = sum(1 for m, h in zip(under["method"], under["horizon"])
               if (m, h) in d.index and float(d[(m, h)]) > 1)
    if both == 0 and lost == len(under):
        return t("forecast.holdout_luck_note")
    if both == 0:
        return t("forecast.holdout_no_repeat_note")
    return t("forecast.holdout_repeat_note", n=both)


def forecast_3m_subtitle(f: pd.DataFrame, horizon: int) -> str:
    """Naive's mean miss on ``forecast_3m.csv`` and how the closest challenger compares."""
    naive = float((f["naive"] - f["actual"]).abs().mean())
    other = float((f["best_other"] - f["actual"]).abs().mean())
    pct = round((other / naive - 1) * 100)
    name = method_name(str(f["best_other_method"].iloc[0]))
    return t("forecast.f3_more" if pct >= 0 else "forecast.f3_less", horizon=horizon,
             miss=fmt_usd(naive), name=name, pct=_pct_points(abs(pct)))


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
    if misses == 0:
        return t("forecast.band_all_held", horizon=horizon, pct=fmt_pct(share), held=n_held, n=n)
    return t("forecast.band_misses", horizon=horizon, pct=fmt_pct(share), held=n_held, n=n,
             in_shock=int((~held & shock).sum()), misses=misses)


def _source_label(source: str) -> str:
    """A crop-estimate source as a table label: "national" -> "National"."""
    return i18n.upper_first(i18n.crop_source_name(source))


def crop_check_table(dev: pd.DataFrame, check: pd.DataFrame, main_source: str) -> pd.DataFrame:
    """Rows for the crop-estimate check: per method, the ``main_source`` estimate on time
    (``dev``), then each source's estimate a month late (``check``). Columns row, horizon,
    ratio."""
    rows = []
    for m in dict.fromkeys(check["method"]):
        name = method_name(str(m))
        d = dev[dev["method"] == m]
        on_time = t("crop_check.row_on_time", method=name, source=_source_label(main_source))
        rows += [(on_time, int(h), float(r)) for h, r in zip(d["horizon"], d["ratio"])]
        for src in dict.fromkeys(check["crop_source"]):
            c = check[(check["method"] == m) & (check["crop_source"] == src)]
            late = t("crop_check.row_late", method=name, source=_source_label(str(src)))
            rows += [(late, int(h), float(r)) for h, r in zip(c["horizon"], c["ratio"])]
    return pd.DataFrame(rows, columns=["row", "horizon", "ratio"])


LEAK_TOLERANCE = 0.05  # a shift this small in error ratio is read as no sign of a leak


def crop_check_subtitle(dev: pd.DataFrame, check: pd.DataFrame, main_source: str, *,
                        rule: str | None = None,
                        tolerance: float = LEAK_TOLERANCE) -> str:
    """The leak verdict (how far the scores moved with every crop estimate a month late),
    then how the other estimate(s) compared with ``main_source`` at that same late timing.
    ``rule`` names the timing rule under test (default "the timing rule")."""
    on_time = dev.set_index(["method", "horizon"])["ratio"]
    late = check[check["crop_source"] == main_source].set_index(["method", "horizon"])["ratio"]
    common = late.index.intersection(on_time.index)
    shift = float((late[common] - on_time[common]).abs().max())
    others = check[check["crop_source"] != main_source]
    cmp = others.set_index(["method", "horizon"]).join(late.rename("main"), how="inner")
    worse = int((cmp["ratio"] > cmp["main"]).sum())
    sources = _join_names([i18n.crop_source_name(s)
                           for s in dict.fromkeys(others["crop_source"].astype(str))])
    return t("crop_check.no_leak" if shift <= tolerance else "crop_check.leak",
             shift=i18n.fmt_number(shift, 2), rule=t("crop_check.default_rule") if rule is None else rule,
             sources=sources, worse=worse, total=len(cmp))


def lira_split(lira: pd.DataFrame, method: str, periods: Sequence[str]) -> pd.DataFrame:
    """``method``'s MAPE ratio by horizon (index) and period (columns, in ``periods`` order)."""
    r = lira[(lira["method"] == method) & lira["period"].isin(list(periods))]
    wide = r.pivot_table(index="horizon", columns="period", values="mape_ratio")
    return wide[list(periods)].rename_axis(columns=None)


def _vs_naive(values) -> tuple[str, dict]:
    """The lira split's key variant ("below", "above", ranges or "mixed") and its fields."""
    pcts = sorted(round((float(v) - 1) * 100) for v in values)
    lo, hi = pcts[0], pcts[-1]
    if hi < 0:
        if lo == hi:
            return "lira.split_below", {"pct": _pct_points(-hi)}
        return "lira.split_below_range", {"low": _pct_points(-hi), "high": _pct_points(-lo)}
    if lo > 0:
        if lo == hi:
            return "lira.split_above", {"pct": _pct_points(lo)}
        return "lira.split_above_range", {"low": _pct_points(lo), "high": _pct_points(hi)}
    return "lira.split_mixed", {"low": _pct_points(-lo), "high": _pct_points(hi)}


def _period_word(period: str) -> str:
    """A lira period's name in words ("calm", "crisis"); other periods keep their key."""
    key = f"lira.period.{period}"
    return t(key) if i18n.has(key) else period


def lira_split_subtitle(lira: pd.DataFrame, method: str, calm: str = "calm",
                        crisis: str = "crisis") -> str:
    w = lira_split(lira, method, (calm, crisis))
    within = round(float((w[calm] - 1).abs().max()) * 100)
    key, values = _vs_naive(w[crisis])
    return t(key, crisis=_period_word(crisis), calm=_period_word(calm),
             within=_pct_points(within), **values)


def lira_p_note(lira: pd.DataFrame, methods: Mapping[str, str]) -> str:
    """Diebold-Mariano p-values over all months (the calm / crisis ones are approximate)."""
    a = lira[lira["period"] == "all"]
    parts = []
    for code, name in methods.items():
        r = a[a["method"] == code].sort_values("horizon")
        ps = " / ".join(fmt_p(p) for p in r["dm_p"])
        hs = " / ".join(str(int(h)) for h in r["horizon"])
        parts.append(t("lira.p_part", name=name, ps=ps, horizons=hs))
    return "; ".join(parts) + "."


def periods_label(periods: Sequence[tuple[str, str]]) -> str:
    """[("2018-05", "2018-12"), ("2021-09", "2023-12")] ->
    "May to December 2018 and September 2021 to December 2023"."""
    def one(a: str, b: str) -> str:
        if a[:4] == b[:4]:
            return t("span.same_year", first=month_name(int(a[5:])), last=month_label(b))
        return t("span.years", first=month_label(a), last=month_label(b))
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
    held = _span(_pct_points(covs[0]), _pct_points(covs[-1]))
    others = ranges[ranges["method"] != base]
    better = int((others["skill"] > 0).sum())
    if better == 0:
        return t("forecast.ranges_none", method=method_name(base), held=held)
    return t("forecast.ranges_some", method=method_name(base), held=held, better=better,
             total=len(others))


def lira_subtitle(lira: pd.DataFrame, trend: Sequence[str], trend_words: str, *,
                  caveat: str | None = None) -> str:
    """The lira table's takeaway over all months: the first horizon, then the gains of the
    ``trend`` methods at the longer horizons (MAPE ratio vs naive). A gain is never stated
    without ``caveat`` (default "which is suggestive only"): several variants were tried,
    so it is suggestive at most."""
    caveat = t("lira.default_caveat") if caveat is None else caveat
    a = lira[(lira["period"] == "all") & (lira["method"] != NAIVE)]
    h1 = int(a["horizon"].min())
    first = a[a["horizon"] == h1]
    beat = int((first["mape_ratio"] < 1).sum())
    if beat == 0:
        lead = t("lira.lead_none", span=_months(h1))
    else:
        lead = t("lira.lead_some", beat=beat, total=len(first), span=_months(h1))
    rest = a[a["method"].isin(list(trend)) & (a["horizon"] > h1)]
    if rest.empty:
        return f"{lead}."
    hs = _join_names([str(int(h)) for h in sorted(rest["horizon"].unique())])
    gains = sorted(round((1 - float(r)) * 100) for r in rest["mape_ratio"])
    lo, hi = gains[0], gains[-1]
    common = dict(horizons=hs, trend=trend_words, caveat=caveat)
    if lo > 0 and lo == hi:
        tail = t("lira.tail_lower", pct=_pct_points(lo), **common)
    elif lo > 0:
        tail = t("lira.tail_lower_range", low=_pct_points(lo), high=_pct_points(hi), **common)
    elif hi > 0:
        tail = t("lira.tail_mixed", low=_pct_points(-lo), high=_pct_points(hi), **common)
    else:
        tail = t("lira.tail_higher", low=_pct_points(-hi), high=_pct_points(-lo), **common)
    return f"{lead}; {tail}."


# --- Data explorer, Downloads, Methods -----------------------------------------------------

OUTLIER_LIMIT = 0.5  # a monthly gap between exchanges beyond ±50% is a source error, not a price
BASE_COLUMN = "usd_kg"  # every crop's site data carries a USD/kg price column


def base_currency() -> tuple[str, str]:
    """(label, column) of the site's base currency, US dollars per kg."""
    return t("unit.usd"), BASE_COLUMN


def number_decimals(fmt: str | None) -> int | None:
    """Decimals shown by an Excel number format: ``"0.00"`` -> 2, ``"#,##0"`` -> 0;
    None (text) stays None."""
    if fmt is None:
        return None
    _, dot, tail = fmt.partition(".")
    return len(tail) - len(tail.lstrip("0")) if dot else 0


def explorer_config(crop: CropConfig, sheets: Mapping, exchange_sheets: Mapping[str, str],
                    sources: Sequence, data_href: str) -> dict:
    """JSON-ready settings for the data explorer, built from the crop's config and its
    workbook spec (``WORKBOOK_SHEETS``), so the explorer and the workbook share files,
    labels and number formats.

    ``exchange_sheets`` maps an exchange name to its monthly sheet; exchanges without one are
    left out. ``data_href`` is the crop's data folder relative to the page. Each exchange's
    ``extras`` are its columns other than the month and the currency prices (the visitor
    can show or hide them); ``source`` and ``terms`` come from the provider row that
    starts with its name."""
    usd_label, usd_col = base_currency()
    currencies = [{"label": usd_label, "column": usd_col},
                  {"label": crop.local_currency.label, "column": crop.local_currency.column}]
    fixed = {"month"} | {c["column"] for c in currencies}
    exchanges = []
    for name in crop.exchanges:
        sheet = exchange_sheets.get(name)
        if sheet is None or sheet not in sheets:
            continue
        file, spec = sheets[sheet]
        columns = [{"key": k, "label": label, "decimals": number_decimals(fmt)}
                   for k, (label, fmt) in spec.items()]
        row = next((r for r in sources if str(r[0]).startswith(name)), None)
        exchanges.append({
            "name": name,
            "file": f"{data_href.rstrip('/')}/{file}",
            "columns": columns,
            "extras": [c["key"] for c in columns if c["key"] not in fixed],
            "source": row[0] if row else None,
            "terms": row[3] if row else None,
        })
    return {"slug": crop.slug, "name": i18n.crop_name(crop), "currencies": currencies,
            "exchanges": exchanges}


def explorer_outlier_note(ref: pd.DataFrame, other: pd.DataFrame, col: str, name: str,
                          ref_name: str, href: str | None,
                          limit: float = OUTLIER_LIMIT) -> str | None:
    """The line under the explorer's table for ``name``: the months its ``col`` price was
    more than ``limit`` away from ``ref_name``'s (likely entry errors in the source), which
    the explorer still shows as published. None when there are none."""
    _, far = split_outliers(gap_series(ref, other, col), limit)
    if far.empty:
        return None
    months = _join_names([month_label(str(m)) for m in far["month"]])
    text = t("explorer.outlier_one" if len(far) == 1 else "explorer.outlier_many",
             months=months, name=name, limit=fmt_pct(limit), ref=ref_name)
    link = (f' <a href="{escape(href)}">{escape(t("explorer.outlier_link"), quote=False)}</a>.'
            if href else "")
    return f"{escape(text, quote=False)}{link}"


def file_size_text(n_bytes: int) -> str:
    """``850_000`` -> ``"830 KB"``, ``1_300_000`` -> ``"1.2 MB"`` (binary units)."""
    kb, mb = n_bytes / 1024, n_bytes / 1024 ** 2
    if mb < 1:
        return t("unit.kb", n=max(1, round(kb)))
    return t("unit.mb", n=i18n.fmt_number(mb, 1) if mb < 10 else round(mb))


DOWNLOAD_ICON = '<svg class="ico" aria-hidden="true"><use href="#download"/></svg>'


def workbook_download_html(href: str, size_bytes: int | None) -> str:
    """The workbook's download button with its size, or a note when the file was not built."""
    if size_bytes is None:
        missing = escape(t("downloads.workbook_missing"), quote=False)
        return f'<p class="chart-error" role="note">{missing}</p>'
    label = t("downloads.button", size=file_size_text(size_bytes))
    return (f'<a class="btn pri" href="{escape(href)}" download>{DOWNLOAD_ICON}'
            f"{escape(label, quote=False)}</a>")


def sheet_list_html(rows: Sequence[tuple[str, str]]) -> str:
    """The workbook's sheets and what each holds, as a two-column table."""
    body = "".join(f"<tr><td>{escape(name)}</td><td>{escape(note)}</td></tr>"
                   for name, note in rows)
    return (
        f'<div class="table-wrap" data-scroll-hint="{escape(scroll_hint())}">'
        '<table class="metric sheets" '
        'data-quarto-disable-processing="true">'
        f'<caption class="visually-hidden">{escape(t("downloads.sheets_caption"))}</caption>'
        f'<thead><tr><th scope="col">{escape(t("downloads.sheet"))}</th>'
        f'<th scope="col">{escape(t("downloads.holds"))}</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def sources_table_html(sources: Sequence) -> str:
    """The source credits: provider (linked), what the site uses, and the credit and terms.
    Rows are a crop's ``WORKBOOK_SOURCES``: (provider, what we use, URL, terms)."""
    body = "".join(
        f'<tr><td><a href="{escape(url)}">{escape(name)}</a></td><td>{escape(what)}</td>'
        f"<td>{escape(terms)}</td></tr>"
        for name, what, url, terms in sources
    )
    return (
        f'<div class="table-wrap" data-scroll-hint="{escape(scroll_hint())}">'
        '<table class="metric sources" '
        'data-quarto-disable-processing="true">'
        f'<caption class="visually-hidden">{escape(t("sources.caption"))}</caption>'
        f'<thead><tr><th scope="col">{escape(t("sources.provider"))}</th>'
        f'<th scope="col">{escape(t("sources.what"))}</th>'
        f'<th scope="col">{escape(t("sources.terms"))}</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def range_held_text(ranges: pd.DataFrame, method: str) -> str:
    """How often ``method``'s 80% range held across horizons: ``"82% to 84%"`` or ``"83%"``."""
    held = sorted({round(v * 100) for v in ranges.loc[ranges["method"] == method, "cov80"]})
    return _span(_pct_points(held[0]), _pct_points(held[-1]))


def methods_facts(dev: pd.DataFrame | None, holdout: pd.DataFrame | None,
                  ranges: pd.DataFrame | None, *, range_method: str,
                  holdout_period: tuple[str, str] | None) -> list[str]:
    """What a crop's forecast tests found, in its forecasting page's words: the development
    scoreboard, the holdout (labelled scored once) and the range's coverage. A fact whose
    data is missing is left out."""
    facts = []
    if dev is not None:
        facts.append(t("methods_page.fact_dev", currency=base_currency()[0],
                       count=count_text(dev["n"]), finding=dev_subtitle(dev)))
    if holdout is not None and holdout_period is not None:
        a, b = holdout_period
        facts.append(t("methods_page.fact_holdout", first=month_label(a), last=month_label(b),
                       finding=holdout_subtitle(holdout)))
    rng = ranges[ranges["method"] == range_method] if ranges is not None else None
    if rng is not None and not rng.empty:
        hs = _join_names([str(int(h)) for h in sorted(rng["horizon"])])
        facts.append(t("methods_page.fact_range", held=range_held_text(ranges, range_method),
                       horizons=hs))
    return facts


def holdout_glossary_sentence(periods: Sequence[tuple[str, tuple[str, str]]]) -> str:
    """The Methods glossary's holdout period, named from each crop's ``HOLDOUT_PERIOD``.

    ``periods`` is ``[(crop name, (first month, last month)), ...]``.
    """
    if not periods:
        return t("methods_page.holdout_none")
    spans = []
    for name, (a, b) in periods:
        n = (pd.Period(b, "M") - pd.Period(a, "M")).n + 1
        spans.append((i18n.lower(name), t("methods_page.holdout_span", first=month_label(a),
                                      last=month_label(b), months=_months(n))))
    (crop, span), rest = spans[0], spans[1:]
    if not rest:
        return t("methods_page.holdout_one", crop=crop, span=span)
    more = "".join(t("methods_page.holdout_more", crop=c, span=s) for c, s in rest)
    return t("methods_page.holdout_many", crop=crop, span=span, more=more)

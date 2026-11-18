"""Plotly chart helpers for the portfolio site (rendered by Quarto at build time).

In a page cell, build a figure with a helper below and pass it to ``show(fig)``. That
writes the figure as JSON into a sized placeholder; ``site/assets/site.js`` loads
plotly.js once (non-blocking), draws every chart, and re-styles them from the page's
CSS variables on load and whenever the colour scheme toggles.

Colours here are the dark-theme design tokens; site.js finds the colours to swap by
the ``meta`` role on each trace (``"fg"`` neutral
marks, ``"accent"`` emphasis marks, ``"accent-fill"`` amber bands) and by the
``name`` of each shape (``"shock"`` amber bands, ``"ref"`` dim reference lines), so keep
those roles when adding charts.

Helpers set no titles: every chart panel's title and takeaway subtitle are page HTML.
Must not import torch or any forecasting method (CI installs requirements-site.txt).
"""
from __future__ import annotations

import base64
import calendar
import copy
import hashlib
import html
import math
from collections.abc import Sequence
from functools import lru_cache

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from hazelnut.site.labels import OTHER_PARTNER, method_name

# Dark-theme tokens (global constraints). site.js swaps in the light ones.
FG = "#eeeae4"
MUTED = "#a39d94"
DIM = "#6f6a63"
LINE = "#26231f"
PANEL = "#121110"
ACCENT = "#c8913f"
ACCENT_SOFT = "rgba(200,145,63,0.14)"
ACCENT_SOFTER = "rgba(200,145,63,0.08)"
TRANSPARENT = "rgba(0,0,0,0)"

FONT = "Geist, system-ui, sans-serif"
MONO = "'Geist Mono', ui-monospace, monospace"

# Plotly config for every chart: no toolbar, resize with the panel.
CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False}

_SHOCK_OPACITY = 0.12


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _axis(**extra) -> dict:
    base = dict(
        showgrid=False, zeroline=False, showline=False, ticks="",
        tickfont=dict(family=MONO, size=11, color=DIM),
        title=dict(font=dict(family=FONT, size=12, color=MUTED)),
        gridcolor=LINE, gridwidth=1, linecolor=LINE, automargin=True,
    )
    return _merge(base, extra)


def layout(**overrides) -> dict:
    """Base layout: transparent backgrounds, Geist, token colours, quiet axes.

    Nested dicts in ``overrides`` are merged, so ``layout(margin={"t": 40})`` keeps
    the other margins.
    """
    base = dict(
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font=dict(family=FONT, size=13, color=FG),
        margin=dict(l=8, r=16, t=8, b=8, pad=4),
        xaxis=_axis(),
        yaxis=_axis(showgrid=True),
        showlegend=False,
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom",
                    font=dict(color=MUTED, size=12), bgcolor=TRANSPARENT),
        hoverlabel=dict(bgcolor=PANEL, bordercolor=LINE,
                        font=dict(family=FONT, size=12, color=FG)),
        hovermode="closest",
        barcornerradius=4,
        dragmode=False,
    )
    return _merge(base, overrides)


def _month_start(month: str) -> pd.Timestamp:
    return pd.Period(month, "M").start_time


def _shock_shapes(shocks: Sequence[tuple[str, str]]) -> list[dict]:
    """Amber bands over each (first month, last month) shock period, behind the data."""
    return [
        dict(type="rect", name="shock", xref="x", yref="paper",
             x0=_month_start(a), x1=pd.Period(b, "M").end_time.normalize() + pd.Timedelta(days=1),
             y0=0, y1=1, fillcolor=ACCENT, opacity=_SHOCK_OPACITY,
             line=dict(width=0), layer="below")
        for a, b in shocks
    ]


def _ref_shape(y: float) -> dict:
    """A thin full-width reference line at ``y`` (site.js gives shapes named "ref" the
    dim colour)."""
    return dict(type="line", name="ref", xref="paper", x0=0, x1=1, yref="y", y0=y, y1=y,
                line=dict(color=DIM, width=1, dash="dash"), layer="below")


def _dates(months) -> pd.Series:
    return pd.to_datetime(pd.Series(months).astype(str) + "-01").reset_index(drop=True)


PRICE_WINDOWS = (("5y", 5), ("10y", 10), ("All", None))
_Y_PAD = 0.05  # share of the visible span added above and below the line


def _y_range(values: pd.Series, log: bool) -> list[float] | None:
    """Padded [min, max] of ``values``; in log10 units for a log axis (Plotly's
    convention for log ranges). None when nothing is plottable."""
    v = values.dropna()
    if log:
        v = v[v > 0].map(math.log10)
    if v.empty:
        return None
    lo, hi = float(v.min()), float(v.max())
    if hi > lo:
        pad = (hi - lo) * _Y_PAD
    else:  # a flat window: give it some height
        pad = 0.05 if log else max(abs(hi) * _Y_PAD, 0.01)
    return [lo - pad, hi + pad]


def price_windows(x: pd.Series, usd: pd.Series, local: pd.Series):
    """For each of 5y, 10y and All: (label, x range, USD y range, local log10 y range).

    Plotly's y autorange ignores the x range, so the y ranges are computed here from the
    points inside each window (ending at the last month)."""
    x = pd.to_datetime(pd.Series(x)).reset_index(drop=True)
    usd, local = pd.Series(usd).reset_index(drop=True), pd.Series(local).reset_index(drop=True)
    last, first = x.max(), x.min()
    out = []
    for label, years in PRICE_WINDOWS:
        start = first if years is None else max(first, last - pd.DateOffset(years=years))
        inside = (x >= start) & (x <= last)
        xr = [start.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")]
        out.append((label, xr, _y_range(usd[inside], log=False),
                    _y_range(local[inside], log=True)))
    return out


def price_history(
    prices: pd.DataFrame,
    shocks: Sequence[tuple[str, str]],
    local_col: str,
    local_label: str,
) -> go.Figure:
    """Monthly price line, USD shown and the local currency one click away, shock
    periods shaded amber.

    ``prices`` needs ``month`` (YYYY-MM), ``usd_kg`` and ``local_col``; ``shocks`` is a
    list of (first month, last month) pairs. ``local_col``/``local_label`` come from the
    crop's ``local_currency`` in ``site/crops.yml``.
    """
    x = pd.to_datetime(prices["month"].astype(str) + "-01").reset_index(drop=True)
    usd = prices["usd_kg"].astype(float).reset_index(drop=True)
    loc = prices[local_col].astype(float).reset_index(drop=True)
    line = dict(color=FG, width=2)
    # USD on yaxis (linear), the local currency on yaxis2 (log, overlaying it). The
    # currency buttons only switch which trace and axis are visible, the period buttons
    # only set ranges, so the two menus never need to know each other's state.
    fig = go.Figure(
        [
            go.Scatter(x=x, y=usd, name="USD", meta="fg", mode="lines",
                       line=line, visible=True, yaxis="y",
                       hovertemplate="$%{y:.2f} /kg<extra></extra>"),
            go.Scatter(x=x, y=loc, name=local_label, meta="fg", mode="lines",
                       line=line, visible=False, yaxis="y2",
                       hovertemplate="%{y:,.2f} " + local_label + "/kg<extra></extra>"),
        ]
    )
    windows = price_windows(x, usd, loc)
    _, all_x, all_usd, all_loc = windows[-1]
    shapes = _shock_shapes(shocks)
    button_style = dict(bgcolor=TRANSPARENT, bordercolor=LINE, borderwidth=1,
                        font=dict(family=FONT, size=12, color=MUTED))
    fig.update_layout(
        layout(
            height=360,
            margin=dict(t=48),
            # One hover box with the month as its title (the date shows once).
            hovermode="x unified",
            yaxis=dict(type="linear", tickprefix="$", tickformat=".2f",
                       autorange=False, range=all_usd),
            # Log axis: a nominal local price can be flat for decades and then explode
            # with the currency's fall; on a log scale both stay readable.
            # Explicit ticks at 1, 2 and 5 x 10^n ("D2"): an overlaying axis would otherwise
            # sync its ticks to yaxis (values like 35.44), and D1 crowds short windows.
            yaxis2=_axis(showgrid=True, overlaying="y", side="left", type="log",
                         tickmode="linear", dtick="D2", tickformat=",~r",
                         autorange=False, range=all_loc, visible=False),
            xaxis=dict(type="date", hoverformat="%b %Y", autorange=False, range=all_x),
            updatemenus=[
                dict(
                    type="buttons", direction="right", showactive=True, active=0,
                    x=0, xanchor="left", y=1.02, yanchor="bottom", pad=dict(t=0, r=0, b=0, l=0),
                    buttons=[
                        dict(label="USD", method="update",
                             args=[{"visible": [True, False]},
                                   {"yaxis.visible": True, "yaxis2.visible": False}]),
                        dict(label=local_label, method="update",
                             args=[{"visible": [False, True]},
                                   {"yaxis.visible": False, "yaxis2.visible": True}]),
                    ],
                    **button_style,
                ),
                dict(
                    type="buttons", direction="right", showactive=True,
                    active=len(windows) - 1,
                    x=1, xanchor="right", y=1.02, yanchor="bottom", pad=dict(t=0, r=0, b=0, l=0),
                    buttons=[
                        dict(label=label, method="relayout",
                             args=[{"xaxis.range": xr, "yaxis.range": yr,
                                    "yaxis2.range": y2r}])
                        for label, xr, yr, y2r in windows
                    ],
                    **button_style,
                ),
            ],
            shapes=shapes,
        )
    )
    return fig


def price_range_fig(rng: pd.DataFrame) -> go.Figure:
    """Fan of where the price could be: 5-95% and 10-90% bands from today's value.

    ``rng`` is ``price_range.csv``: one row per horizon with ``target_month``,
    ``q05 q10 q50 q90 q95`` and the same ``from_month``/``from_usd`` on every row.
    """
    rng = rng.sort_values("horizon")
    start, today = str(rng["from_month"].iloc[0]), float(rng["from_usd"].iloc[0])
    x = [start, *rng["target_month"].astype(str)]

    def col(name: str) -> list[float]:
        return [today, *rng[name].astype(float)]

    hover = "%{x}<br>$%{y:.2f}<extra>%{meta}</extra>"
    band = dict(mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False)
    fig = go.Figure(
        [
            go.Scatter(x=x, y=col("q05"), **band, meta="accent-fill"),
            go.Scatter(x=x, y=col("q95"), **band, fill="tonexty", fillcolor=ACCENT_SOFTER,
                       meta="accent-fill", name="9 in 10"),
            go.Scatter(x=x, y=col("q10"), **band, meta="accent-fill"),
            go.Scatter(x=x, y=col("q90"), **band, fill="tonexty", fillcolor=ACCENT_SOFT,
                       meta="accent-fill", name="8 in 10"),
            go.Scatter(x=x, y=col("q50"), mode="lines", name="Middle",
                       line=dict(color=FG, width=2), meta="fg",
                       hovertemplate="%{x}<br>middle $%{y:.2f}<extra></extra>"),
            go.Scatter(x=x, y=[today] * len(x), mode="lines", name="Today's price",
                       line=dict(color=ACCENT, width=1, dash="dash"), meta="accent",
                       hoverinfo="skip"),
            go.Scatter(x=[start], y=[today], mode="markers", name="Today",
                       marker=dict(color=ACCENT, size=10, line=dict(width=2, color=PANEL)),
                       meta="accent",
                       hovertemplate="%{x}<br>today $%{y:.2f}<extra></extra>"),
        ]
    )
    for t in fig.data[:4]:
        t.hovertemplate = hover
    fig.update_layout(
        layout(
            height=300,
            hovermode="x",
            xaxis=dict(type="category", tickvals=x,
                       ticktext=["Today", *[f"+{h} mo" for h in rng["horizon"]]]),
            yaxis=dict(tickprefix="$", tickformat=".2f"),
        )
    )
    return fig


def bar_top(top: pd.DataFrame) -> go.Figure:
    """Horizontal bars of export share by destination, largest at the top and the
    "Other" bucket always last.

    ``top`` is ``exports_top.csv``: ``partner, net_kg, fob_usd, share`` (share of net_kg).
    """
    # Plotly draws the first category at the bottom: "Other" first, then smallest to largest.
    is_other = top["partner"] == OTHER_PARTNER
    top = pd.concat([top[is_other], top[~is_other].sort_values("share", ascending=True)])
    fig = go.Figure(
        go.Bar(
            x=top["share"], y=top["partner"], orientation="h", meta="fg",
            marker=dict(color=FG, opacity=0.8),
            text=top["share"], texttemplate="%{x:.0%}", textposition="outside",
            textfont=dict(family=MONO, size=11, color=MUTED), cliponaxis=False,
            customdata=list(zip(top["net_kg"] / 1000, top["fob_usd"] / 1e6)),
            hovertemplate=("%{y}<br>%{x:.1%} of exports<br>%{customdata[0]:,.0f} t"
                           " · $%{customdata[1]:,.0f}m<extra></extra>"),
        )
    )
    fig.update_layout(
        layout(
            height=max(160, 32 * len(top) + 16),
            bargap=0.35,
            xaxis=dict(visible=False, range=[0, float(top["share"].max()) * 1.18]),
            yaxis=dict(showgrid=False, tickfont=dict(family=FONT, size=12, color=MUTED)),
        )
    )
    return fig


def crop_vs_price(crop: pd.DataFrame, x_col: str) -> go.Figure:
    """Crop estimate against the season's average USD price; latest season in amber.

    ``crop`` is ``crop_by_year.csv``. Rows missing either value are left out; the
    latest remaining season is highlighted (it may be a season still in progress).
    ``x_col`` is the crop-size column to plot (per-crop builders own the names). With
    no complete rows the figure has no traces; the page shows its empty state.
    """
    df = crop.dropna(subset=[x_col, "season_avg_usd"]).sort_values("year")
    fig = go.Figure()
    if not df.empty:
        latest, rest = df.iloc[[-1]], df.iloc[:-1]
        hover = "%{text}<br>%{x:,.0f} t crop<br>$%{y:.2f} /kg season average<extra></extra>"
        fig.add_traces(
            [
                go.Scatter(x=rest[x_col], y=rest["season_avg_usd"], mode="markers",
                           name="Earlier seasons", meta="fg", text=rest["season"],
                           marker=dict(color=FG, opacity=0.75, size=8),
                           hovertemplate=hover),
                go.Scatter(x=latest[x_col], y=latest["season_avg_usd"], mode="markers+text",
                           name=str(latest["season"].iloc[0]), meta="accent",
                           text=latest["season"], textposition="top center",
                           textfont=dict(family=MONO, size=11, color=MUTED),
                           marker=dict(color=ACCENT, size=12, line=dict(width=2, color=PANEL)),
                           hovertemplate=hover),
            ]
        )
    fig.update_layout(
        layout(
            height=300,
            xaxis=dict(showgrid=False, tickformat="~s", ticksuffix=" t",
                       title=dict(text="Crop estimate")),
            yaxis=dict(tickprefix="$", tickformat=".2f",
                       title=dict(text="Season average")),
        )
    )
    return fig


# --- Analyses pages ---------------------------------------------------------------------

def season_profile(profile: pd.DataFrame) -> go.Figure:
    """Average change from the season's mean by month (bars), with a thin whisker over the
    middle half of seasons. ``profile`` is ``page_helpers.seasonal_profile``'s output."""
    labels = [calendar.month_abbr[int(m)] for m in profile["month"]]
    wx, wy = [], []
    for lab, lo, hi in zip(labels, profile["q25"], profile["q75"]):
        wx += [lab, lab, None]
        wy += [float(lo), float(hi), None]
    fig = go.Figure([
        go.Bar(x=labels, y=[float(v) for v in profile["mean"]], name="Average month",
               meta="fg", marker=dict(color=FG, opacity=0.8),
               customdata=list(zip(profile["label"], profile["q25"], profile["q75"])),
               hovertemplate=("%{customdata[0]}<br>average %{y:+.1%}<br>middle half of seasons "
                              "%{customdata[1]:+.1%} to %{customdata[2]:+.1%}<extra></extra>")),
        go.Scatter(x=wx, y=wy, mode="lines", name="Middle half of seasons", meta="fg",
                   line=dict(color=FG, width=1.5), opacity=0.45, hoverinfo="skip"),
    ])
    fig.update_layout(layout(
        height=320, showlegend=True, bargap=0.45, margin=dict(t=40),
        xaxis=dict(type="category"),
        yaxis=dict(tickformat="+.0%", showgrid=True),
    ))
    return fig


def share_lines(shares: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    """One line per column (a partner's share by year), labelled at its last point;
    ``highlight`` is drawn in amber."""
    x = [int(y) for y in shares.index]
    traces = []
    for col in shares.columns:
        hl = col == highlight
        traces.append(go.Scatter(
            x=x, y=[float(v) for v in shares[col]], name=str(col), mode="lines+text",
            text=[""] * (len(x) - 1) + [str(col)], textposition="middle right",
            textfont=dict(family=FONT, size=12, color=MUTED), cliponaxis=False,
            meta="accent" if hl else "fg", opacity=1 if hl else 0.75,
            line=dict(color=ACCENT if hl else FG, width=2 if hl else 1.5),
            hovertemplate=f"{html.escape(str(col))} %{{y:.0%}}<extra></extra>",
        ))
    fig = go.Figure(traces)
    fig.update_layout(layout(
        height=340, hovermode="x unified", margin=dict(r=96),
        xaxis=dict(tickformat="d"),
        yaxis=dict(tickformat=".0%", rangemode="tozero"),
    ))
    return fig


def compare_lines(x, a, b, a_name: str, b_name: str, *, prefix: str = "$",
                  suffix: str = " /kg", shocks: Sequence[tuple[str, str]] = ()) -> go.Figure:
    """Two monthly series on one axis: ``a`` solid, ``b`` dotted and fainter. Gaps (NaN)
    stay gaps. ``x`` is YYYY-MM months; ``shocks`` are shaded amber."""
    xs = _dates(x)

    def hover(name: str) -> str:
        return f"{html.escape(name)} {prefix}%{{y:,.2f}}{suffix}<extra></extra>"

    fig = go.Figure([
        go.Scatter(x=xs, y=list(a), name=a_name, mode="lines", meta="fg",
                   line=dict(color=FG, width=2), connectgaps=False, hovertemplate=hover(a_name)),
        go.Scatter(x=xs, y=list(b), name=b_name, mode="lines", meta="fg", opacity=0.75,
                   line=dict(color=FG, width=1.5, dash="dot"), connectgaps=False,
                   hovertemplate=hover(b_name)),
    ])
    fig.update_layout(layout(
        height=340, showlegend=True, hovermode="x unified", margin=dict(t=40),
        xaxis=dict(type="date", hoverformat="%b %Y"),
        yaxis=dict(tickprefix=prefix, tickformat=".2f"),
        shapes=_shock_shapes(shocks),
    ))
    return fig


def gap_line(x, gap, median: float) -> go.Figure:
    """A monthly percent gap as a line, with a zero line and its median dashed in amber.
    Months missing from ``x`` stay gaps in the line."""
    s = pd.Series(list(gap), index=pd.PeriodIndex(pd.Series(x).astype(str), freq="M"), dtype=float)
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))
    xs = pd.Series(s.index.to_timestamp())
    ys = [None if pd.isna(v) else float(v) for v in s]
    label = f"Median {median:+.1%}".replace("-", "−")
    fig = go.Figure([
        go.Scatter(x=xs, y=ys, name="Gap", mode="lines", meta="fg",
                   line=dict(color=FG, width=1.5), connectgaps=False,
                   hovertemplate="%{y:+.1%}<extra></extra>"),
        go.Scatter(x=[xs.min(), xs.max()], y=[median, median], name=label, mode="lines",
                   meta="accent", line=dict(color=ACCENT, width=1.5, dash="dash"),
                   hoverinfo="skip"),
    ])
    fig.update_layout(layout(
        height=280, showlegend=True, hovermode="x unified", margin=dict(t=40),
        xaxis=dict(type="date", hoverformat="%b %Y"),
        yaxis=dict(tickformat="+.0%"),
        shapes=[_ref_shape(0)],
    ))
    return fig


def labeled_scatter(df: pd.DataFrame, x: str, y: str, label: str, highlight: Sequence = (),
                    *, x_title: str = "", y_title: str = "", x_hover: str = ",.1f",
                    y_hover: str = ",.0f", y_suffix: str = "") -> go.Figure:
    """Points of ``y`` against ``x``; rows whose ``label`` is in ``highlight`` are amber and
    labelled. Rows missing either value are left out."""
    d = df.dropna(subset=[x, y])
    is_hl = d[label].isin(list(highlight))
    hover = (f"%{{text}}<br>{html.escape(x_title)} %{{x:{x_hover}}}<br>"
             f"{html.escape(y_title)} %{{y:{y_hover}}}{html.escape(y_suffix)}<extra></extra>")

    def trace(part: pd.DataFrame, hl: bool) -> go.Scatter:
        return go.Scatter(
            x=list(part[x]), y=list(part[y]), text=[str(v) for v in part[label]],
            mode="markers+text" if hl else "markers", meta="accent" if hl else "fg",
            name="Highlighted" if hl else "Other years", textposition="top center",
            textfont=dict(family=MONO, size=11, color=MUTED),
            marker=(dict(color=ACCENT, size=11, line=dict(width=2, color=PANEL)) if hl
                    else dict(color=FG, size=8, opacity=0.7)),
            hovertemplate=hover,
        )

    fig = go.Figure([trace(d[~is_hl], False), trace(d[is_hl], True)])
    fig.update_layout(layout(
        height=320,
        xaxis=dict(title=dict(text=x_title), showgrid=False),
        yaxis=dict(title=dict(text=y_title), tickformat="~s", ticksuffix=y_suffix),
    ))
    return fig


def forecast_vs_actual(f: pd.DataFrame, other_name: str,
                       shocks: Sequence[tuple[str, str]] = ()) -> go.Figure:
    """The actual price, naive's forecast (amber) and one challenger's (dotted), by target
    month. ``f`` is ``forecast_3m.csv``: ``target_month, actual, naive, best_other``."""
    xs = _dates(f["target_month"])
    naive = method_name("naive")

    def line(col: str, name: str, meta: str, **style) -> go.Scatter:
        return go.Scatter(x=xs, y=[float(v) for v in f[col]], name=name, mode="lines",
                          meta=meta, hovertemplate=f"{html.escape(name)} $%{{y:.2f}}<extra></extra>",
                          **style)

    fig = go.Figure([
        line("actual", "Actual", "fg", line=dict(color=FG, width=2)),
        line("naive", naive, "accent", line=dict(color=ACCENT, width=1.5)),
        line("best_other", other_name, "fg", opacity=0.6,
             line=dict(color=FG, width=1.5, dash="dot")),
    ])
    fig.update_layout(layout(
        height=360, showlegend=True, hovermode="x unified", margin=dict(t=40),
        xaxis=dict(type="date", hoverformat="%b %Y"),
        yaxis=dict(tickprefix="$", tickformat=".2f"),
        shapes=_shock_shapes(shocks),
    ))
    return fig


def range_band(band: pd.DataFrame) -> go.Figure:
    """A backtest's 8-in-10 range (q10..q90, amber band) against the actual price, with the
    months that fell outside it marked. ``band`` is ``range_band_3m.csv``."""
    xs = _dates(band["target_month"])
    actual = band["actual"].astype(float).reset_index(drop=True)
    lo = band["q10"].astype(float).reset_index(drop=True)
    hi = band["q90"].astype(float).reset_index(drop=True)
    out = (actual < lo) | (actual > hi)
    fig = go.Figure([
        go.Scatter(x=xs, y=list(lo), mode="lines", line=dict(width=0), meta="accent-fill",
                   showlegend=False, hoverinfo="skip", name="Range low"),
        go.Scatter(x=xs, y=list(hi), mode="lines", line=dict(width=0), meta="accent-fill",
                   fill="tonexty", fillcolor=ACCENT_SOFT, name="8-in-10 range",
                   customdata=list(lo),
                   hovertemplate="range $%{customdata:.2f} to $%{y:.2f}<extra></extra>"),
        go.Scatter(x=xs, y=list(actual), mode="lines", name="Actual", meta="fg",
                   line=dict(color=FG, width=1.5), hovertemplate="actual $%{y:.2f}<extra></extra>"),
        go.Scatter(x=list(xs[out]), y=list(actual[out]), mode="markers",
                   name="Outside the range", meta="accent",
                   marker=dict(color=ACCENT, size=6), hoverinfo="skip"),
    ])
    fig.update_layout(layout(
        height=340, showlegend=True, hovermode="x unified", margin=dict(t=40),
        xaxis=dict(type="date", hoverformat="%b %Y"),
        yaxis=dict(tickprefix="$", tickformat=".2f"),
    ))
    return fig


def ratio_bars(wide: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    """Grouped bars of error ratios by horizon (index, months), one bar per column, with a
    dashed line at 1 (naive). ``highlight`` is amber."""
    x = [f"{int(h)} mo" for h in wide.index]
    bars = []
    for col in wide.columns:
        hl = col == highlight
        bars.append(go.Bar(
            x=x, y=[float(v) for v in wide[col]], name=str(col),
            meta="accent" if hl else "fg",
            marker=dict(color=ACCENT if hl else FG, opacity=1 if hl else 0.55),
            texttemplate="%{y:.2f}", textposition="outside", cliponaxis=False,
            textfont=dict(family=MONO, size=11, color=MUTED),
            hovertemplate=f"{html.escape(str(col))} %{{y:.2f}}<extra></extra>",
        ))
    top = max(1.0, float(wide.max().max()))
    fig = go.Figure(bars)
    fig.update_layout(layout(
        height=300, showlegend=True, barmode="group", bargap=0.3, margin=dict(t=40),
        xaxis=dict(type="category"),
        yaxis=dict(range=[0, top * 1.15], tickformat=".1f"),
        shapes=[_ref_shape(1)],
    ))
    return fig


@lru_cache(maxsize=1)
def _plotlyjs_source() -> tuple[str, str]:
    """CDN URL and SRI hash of the plotly.js build bundled with this plotly.py."""
    from plotly.offline import get_plotlyjs, get_plotlyjs_version

    digest = hashlib.sha256(get_plotlyjs().encode("utf-8")).digest()
    url = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"
    return url, "sha256-" + base64.b64encode(digest).decode("ascii")


def to_html(fig: go.Figure) -> str:
    """The figure as a placeholder ``<div>`` that ``site.js`` draws.

    The div is sized to the figure height (default 360px) and shows a loading
    skeleton until plotly.js arrives; the figure JSON sits in a JSON script block.
    """
    spec = {**fig.to_plotly_json(), "config": CONFIG}
    spec.pop("frames", None)
    # "<\/" is the same string to JSON, and cannot close the script block early.
    payload = pio.to_json(spec, validate=False).replace("</", "<\\/")
    height = int(fig.layout.height or 360)
    src, sri = _plotlyjs_source()
    return (
        f'<div class="chart chart-skeleton" style="height:{height}px" data-plotly'
        f' data-plotly-src="{html.escape(src)}" data-plotly-sri="{html.escape(sri)}">'
        f'<script type="application/json">{payload}</script></div>'
    )


def show(fig: go.Figure) -> None:
    """Display ``fig`` in a Quarto page cell (see ``to_html``).

    Emitted as a markdown raw-HTML block rather than a text/html output: Quarto adds
    require.js and a second jQuery to any page with text/html cell output.
    """
    import IPython.display

    IPython.display.display(IPython.display.Markdown("```{=html}\n" + to_html(fig) + "\n```\n"))

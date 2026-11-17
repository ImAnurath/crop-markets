"""Plotly chart helpers for the portfolio site (rendered by Quarto at build time).

In a page cell, build a figure with a helper below and pass it to ``show(fig)``. That
writes the figure as JSON into a sized placeholder; ``site/assets/site.js`` loads
plotly.js once (non-blocking), draws every chart, and re-styles them from the page's
CSS variables on load and whenever the colour scheme toggles.

Colours here are the dark-theme design tokens; site.js finds the colours to swap by
the ``meta`` role on each trace (``"fg"`` neutral
marks, ``"accent"`` emphasis marks, ``"accent-fill"`` amber bands) and by the
``name`` of each shape (``"shock"``), so keep those roles when adding charts.

Helpers set no titles: every chart panel's title and takeaway subtitle are page HTML.
Must not import torch or any forecasting method (CI installs requirements-site.txt).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import html
from collections.abc import Sequence
from functools import lru_cache

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

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
    x = pd.to_datetime(prices["month"].astype(str) + "-01")
    line = dict(color=FG, width=2)
    fig = go.Figure(
        [
            go.Scatter(x=x, y=prices["usd_kg"], name="USD", meta="fg", mode="lines",
                       line=line, visible=True,
                       hovertemplate="%{x|%b %Y}<br>$%{y:.2f} /kg<extra></extra>"),
            go.Scatter(x=x, y=prices[local_col], name=local_label, meta="fg", mode="lines",
                       line=line, visible=False,
                       hovertemplate="%{x|%b %Y}<br>%{y:,.2f} " + local_label + "/kg<extra></extra>"),
        ]
    )
    shapes = [
        dict(type="rect", name="shock", xref="x", yref="paper",
             x0=_month_start(a), x1=pd.Period(b, "M").end_time.normalize() + pd.Timedelta(days=1),
             y0=0, y1=1, fillcolor=ACCENT, opacity=_SHOCK_OPACITY,
             line=dict(width=0), layer="below")
        for a, b in shocks
    ]
    button_style = dict(bgcolor=TRANSPARENT, bordercolor=LINE, borderwidth=1,
                        font=dict(family=FONT, size=12, color=MUTED))
    fig.update_layout(
        layout(
            height=360,
            margin=dict(t=48),
            hovermode="x",
            yaxis=dict(tickprefix="$", tickformat=".2f"),
            xaxis=dict(
                type="date",
                hoverformat="%b %Y",
                rangeselector=dict(
                    buttons=[
                        dict(count=5, label="5y", step="year", stepmode="backward"),
                        dict(count=10, label="10y", step="year", stepmode="backward"),
                        dict(label="All", step="all"),
                    ],
                    x=1, xanchor="right", y=1.02, yanchor="bottom",
                    activecolor=LINE, **button_style,
                ),
            ),
            updatemenus=[
                dict(
                    type="buttons", direction="right", showactive=True, active=0,
                    x=0, xanchor="left", y=1.02, yanchor="bottom", pad=dict(t=0, r=0, b=0, l=0),
                    buttons=[
                        dict(label="USD", method="update",
                             args=[{"visible": [True, False]},
                                   {"yaxis.type": "linear", "yaxis.tickprefix": "$",
                                    "yaxis.tickformat": ".2f", "yaxis.autorange": True}]),
                        # Log axis: a nominal local price can be flat for decades and then
                        # explode with the currency's fall; on a log scale both stay readable.
                        dict(label=local_label, method="update",
                             args=[{"visible": [False, True]},
                                   {"yaxis.type": "log", "yaxis.tickprefix": "",
                                    "yaxis.tickformat": ",~r", "yaxis.autorange": True}]),
                    ],
                    **button_style,
                )
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
    """Horizontal bars of export share by destination, largest at the top.

    ``top`` is ``exports_top.csv``: ``partner, net_kg, fob_usd, share`` (share of net_kg).
    """
    top = top.sort_values("share", ascending=True)
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

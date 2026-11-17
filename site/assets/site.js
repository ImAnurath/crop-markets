/* Site behaviour: sprite icons in the nav, and Plotly charts that follow the colour scheme.
   The scheme itself (stored choice, else dark) is Quarto's; this file only reacts to it.
   Charts are written by hazelnut.site.charts.show() as
     <div class="chart chart-skeleton" data-plotly data-plotly-src=… data-plotly-sri=…>
       <script type="application/json">{data, layout, config}</script></div>
   This file loads plotly.js once (without blocking the page) and draws them. */
(function () {
  "use strict";

  var SVG = "http://www.w3.org/2000/svg";

  function icon(name) {
    var svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", "ico");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS(SVG, "use");
    use.setAttribute("href", "#" + name);
    svg.appendChild(use);
    return svg;
  }

  function decorateNav() {
    document.querySelectorAll(".quarto-color-scheme-toggle").forEach(function (btn) {
      if (!btn.querySelector("svg.ico")) btn.appendChild(icon("contrast"));
      btn.setAttribute("title", "Switch light / dark");
    });
    document.querySelectorAll('.navbar a.nav-link[href$=".xlsx"]').forEach(function (a) {
      if (!a.querySelector("svg.ico")) a.insertBefore(icon("download"), a.firstChild);
    });
  }

  // ---- Theme tokens -------------------------------------------------------
  function tokens() {
    var cs = getComputedStyle(document.documentElement);
    var get = function (n) { return cs.getPropertyValue(n).trim(); };
    return { fg: get("--fg"), muted: get("--muted"), dim: get("--dim"), line: get("--line"),
             panel: get("--panel"), accent: get("--accent") };
  }

  function rgba(hex, alpha) {
    var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
    if (!m) return hex;
    return "rgba(" + parseInt(m[1], 16) + "," + parseInt(m[2], 16) + "," + parseInt(m[3], 16) + "," + alpha + ")";
  }

  function alphaOf(color) {
    var m = /rgba\([^)]*,\s*([\d.]+)\s*\)$/.exec(color || "");
    return m ? parseFloat(m[1]) : 0.14;
  }

  function set(obj, key, patch) {
    obj[key] = Object.assign({}, obj[key] || {}, patch);
  }

  /* Returns themed copies of a figure's data and layout. Colours are found by role:
     trace.meta "fg" (neutral marks), "accent" (emphasis), "accent-fill" (amber bands),
     and shape.name "shock". Trace arrays are shared, not copied. */
  function themed(data, layout, t) {
    var lay = Object.assign({}, layout);
    set(lay, "font", { color: t.fg });
    set(lay, "hoverlabel", { bgcolor: t.panel, bordercolor: t.line });
    lay.hoverlabel.font = Object.assign({}, lay.hoverlabel.font, { color: t.fg });
    if (lay.legend) { set(lay, "legend", {}); lay.legend.font = Object.assign({}, lay.legend.font, { color: t.muted }); }
    Object.keys(lay).forEach(function (k) {
      if (!/^[xy]axis\d*$/.test(k)) return;
      var ax = lay[k] = Object.assign({}, lay[k], { gridcolor: t.line, linecolor: t.line });
      ax.tickfont = Object.assign({}, ax.tickfont, { color: t.dim });
      if (ax.title) ax.title = Object.assign({}, ax.title, { font: Object.assign({}, ax.title.font, { color: t.muted }) });
      if (ax.rangeselector) {
        ax.rangeselector = Object.assign({}, ax.rangeselector, { bordercolor: t.line, activecolor: t.line });
        ax.rangeselector.font = Object.assign({}, ax.rangeselector.font, { color: t.muted });
      }
    });
    if (lay.updatemenus) lay.updatemenus = lay.updatemenus.map(function (u) {
      return Object.assign({}, u, { bordercolor: t.line, font: Object.assign({}, u.font, { color: t.muted }) });
    });
    if (lay.shapes) lay.shapes = lay.shapes.map(function (s) {
      return s.name === "shock" ? Object.assign({}, s, { fillcolor: t.accent }) : s;
    });

    var out = (data || []).map(function (d) {
      var role = d.meta, tr = Object.assign({}, d);
      if (role === "fg" || role === "accent") {
        var c = role === "fg" ? t.fg : t.accent;
        if (!d.type || d.type === "scatter") set(tr, "line", { color: c });
        set(tr, "marker", { color: c });
        if (d.marker && d.marker.line && d.marker.line.width) tr.marker.line = Object.assign({}, d.marker.line, { color: t.panel });
        if (d.textfont) set(tr, "textfont", { color: t.muted });
      } else if (role === "accent-fill" && d.fillcolor) {
        tr.fillcolor = rgba(t.accent, alphaOf(d.fillcolor));
      }
      return tr;
    });
    return { data: out, layout: lay };
  }

  // ---- Charts -------------------------------------------------------------
  function charts() { return document.querySelectorAll("[data-plotly]"); }

  function fail(div) {
    div.classList.remove("chart-skeleton");
    div.classList.add("chart-error");
    div.textContent = "This chart could not load (the charting library did not download). " +
      "Reload the page to try again; the numbers are also in the Excel workbook.";
  }

  function draw(div, t) {
    var spec;
    try { spec = JSON.parse(div.querySelector("script[type='application/json']").textContent); }
    catch (e) { fail(div); return; }
    var th = themed(spec.data, spec.layout, t);
    div.dataset.schemeFg = t.fg;
    window.Plotly.newPlot(div, th.data, th.layout, spec.config || {}).then(function () {
      div.classList.remove("chart-skeleton");
    }, function () { fail(div); });
  }

  // Re-theme drawn charts from their current state, so a user's choices (USD/TL,
  // 5y/10y/All) survive the scheme switch.
  function retheme(div, t) {
    if (div.dataset.schemeFg === t.fg) return;
    div.dataset.schemeFg = t.fg;
    var th = themed(div.data, div.layout, t);
    window.Plotly.react(div, th.data, th.layout);
  }

  var pending = false;
  function sync() {
    pending = false;
    if (!window.Plotly) return;
    var t = tokens();
    if (!t.fg) return;
    charts().forEach(function (div) {
      try {
        if (div.classList.contains("js-plotly-plot")) retheme(div, t);
        else if (!div.classList.contains("chart-error")) draw(div, t);
      } catch (e) { fail(div); }
    });
  }
  function schedule() {
    if (pending) return;
    pending = true;
    window.requestAnimationFrame(sync);
  }

  function loadPlotly() {
    var first = charts()[0];
    if (!first) return;
    if (window.Plotly) { schedule(); return; }
    var s = document.createElement("script");
    s.src = first.getAttribute("data-plotly-src");
    var sri = first.getAttribute("data-plotly-sri");
    if (sri) { s.integrity = sri; s.crossOrigin = "anonymous"; }
    s.async = true;
    s.onload = schedule;
    s.onerror = function () { charts().forEach(fail); };
    document.head.appendChild(s);
  }

  function init() {
    decorateNav();
    loadPlotly();
    // The scheme toggle flips body classes; a re-enabled stylesheet may finish
    // loading a moment later, so listen for both.
    new MutationObserver(function () { schedule(); setTimeout(schedule, 250); }).observe(document.body, { attributes: true, attributeFilter: ["class"] });
    document.querySelectorAll("link.quarto-color-scheme").forEach(function (l) {
      l.addEventListener("load", schedule);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

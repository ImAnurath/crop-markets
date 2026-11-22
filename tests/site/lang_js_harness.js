// Runs site/filters/lang-detect.js or site/assets/site.js in a Node vm against a stub
// window/document/localStorage/navigator/location, and prints what happened as JSON.
// Used by tests/site/test_lang_js.py:  node lang_js_harness.js <script> <case JSON>
"use strict";
const fs = require("fs");
const vm = require("vm");

const [script, caseJson] = process.argv.slice(2);
const c = JSON.parse(caseJson);
const out = { replaced: null, stored: undefined, switch: null };

class Storage {
  constructor(data) { this.data = Object.assign({}, data); }
  getItem(k) { return Object.prototype.hasOwnProperty.call(this.data, k) ? this.data[k] : null; }
  setItem(k, v) { this.data[k] = String(v); }
  removeItem(k) { delete this.data[k]; }
}
// "real": a Storage; "shim": the colour-scheme shim's plain-object memory store;
// "throws": blocked storage (reading window.localStorage throws).
let store = null;
if (c.storage === "real") store = new Storage(c.stored || {});
if (c.storage === "shim") {
  const m = Object.assign({}, c.stored || {});
  store = { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: (k) => { delete m[k]; } };
}

function element(tag) {
  const e = {
    tagName: tag.toUpperCase(), attrs: {}, children: [], listeners: {}, textContent: "", className: "", href: "",
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    appendChild(ch) { this.children.push(ch); return ch; },
    insertBefore(ch, ref) {
      const i = this.children.indexOf(ref);
      if (i < 0) this.children.push(ch); else this.children.splice(i, 0, ch);
      return ch;
    },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  Object.defineProperty(e, "firstChild", { get() { return this.children[0] || null; } });
  return e;
}

const links = {};
for (const [lang, dataHref] of Object.entries(c.alternates || {})) {
  const l = element("link");
  l.setAttribute("rel", "alternate"); l.setAttribute("hreflang", lang); l.setAttribute("data-href", dataHref);
  links[lang] = l;
}
const tools = element("div");
const theme = element("button");
tools.appendChild(theme);
const winListeners = {};
const href = c.url;
const u = new URL(href);
const location = {
  href, search: u.search, hash: u.hash, pathname: u.pathname,
  replace(x) { out.replaced = x; },
};
const document = {
  readyState: "complete",
  documentElement: { lang: c.lang },
  head: element("head"),
  body: element("body"),
  createElement: element,
  createElementNS: (ns, tag) => element(tag),
  getElementById: (id) => (id === "site-strings" && c.strings ? { textContent: JSON.stringify(c.strings) } : null),
  querySelector(sel) {
    if (sel === ".quarto-navbar-tools") return tools;
    const m = /^link\[rel="alternate"\]\[hreflang="([^"]+)"\]\[data-href\]$/.exec(sel);
    if (m) return links[m[1]] || null;
    return null;
  },
  querySelectorAll: (sel) => (sel === ".quarto-color-scheme-toggle" ? [theme] : []),
};
const ctx = {
  document, location, URL, Storage, JSON, Object, Array, String, WeakSet, Math, parseInt, parseFloat,
  navigator: { languages: c.languages, language: (c.languages || [])[0] },
  MutationObserver: class { observe() {} },
  requestAnimationFrame: () => 0,
  setTimeout: () => 0,
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
  addEventListener(t, f) { (winListeners[t] = winListeners[t] || []).push(f); },
};
Object.defineProperty(ctx, "localStorage", {
  configurable: true,
  get() { if (c.storage === "throws") throw new Error("SecurityError"); return store; },
});
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(script, "utf8"), ctx, { filename: script });

// The switch, if site.js built one: click its link after an in-page hash change.
const box = tools.children.find((e) => e.className === "lang-switch");
if (box) {
  out.switch = {
    label: box.getAttribute("aria-label"),
    items: box.children.map((e) => ({ tag: e.tagName, text: e.textContent, current: e.getAttribute("aria-current"),
                                      lang: e.getAttribute("lang"), title: e.getAttribute("title") })),
  };
  const a = box.children.find((e) => e.tagName === "A");
  if (a && c.clickAfterHash !== undefined) {
    location.hash = c.clickAfterHash;
    (winListeners.hashchange || []).forEach((f) => f());
    out.switch.hrefAfterHashchange = a.href;
    (a.listeners.click || []).forEach((f) => f());
    out.switch.clickedHref = a.href;
  }
  out.switch.themeTitle = theme.getAttribute("title");
}
try { out.stored = ctx.localStorage ? ctx.localStorage.getItem("crop-markets-lang") : null; } catch (e) { out.stored = "THREW"; }
process.stdout.write(JSON.stringify(out));

/* First visit (inlined into <head> by lang-links.lua, after the hreflang links): a visitor
   whose browser lists Turkish before English goes to this page's Turkish counterpart,
   once. Never on a Turkish page, never once a choice is stored, and never without
   working storage: there the switch's choice could not be remembered either, so the
   visitor would be sent back to Turkish on every English page. */
(function () {
  "use strict";
  var KEY = "crop-markets-lang";
  if (document.documentElement.lang !== "en") return;
  var alt = document.querySelector('link[rel="alternate"][hreflang="tr"][data-href]');
  if (!alt) return;
  var store;
  try {
    store = window.localStorage;
    // Where storage is blocked, the colour-scheme shim swaps in a plain-object memory
    // store, which forgets on every page load.
    if (!(store instanceof Storage) || store.getItem(KEY) !== null) return;
  } catch (e) { return; }
  var langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
  for (var i = 0; i < langs.length; i++) {
    var m = /^(en|tr)(-|$)/i.exec(langs[i] || "");
    if (!m) continue;
    if (m[1].toLowerCase() !== "tr") return;
    try {
      store.setItem(KEY, "tr");
      if (store.getItem(KEY) !== "tr") return;
    } catch (e) { return; }
    var url = new URL(alt.getAttribute("data-href"), location.href);
    url.search = location.search;
    url.hash = location.hash;
    location.replace(url.href);
    return;
  }
})();

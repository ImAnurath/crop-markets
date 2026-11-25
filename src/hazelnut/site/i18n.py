"""The site's active language (English or Turkish), its strings and its number and date
formats.

Quarto renders the site once per language profile (``site/_quarto-en.yml``,
``site/_quarto-tr.yml``; ``scripts/render_site.py`` runs both) and passes the active
profile to page cells as ``QUARTO_PROFILE``. Outside Quarto (tests, scripts) the
``SITE_LANG`` variable picks the language; English is the default. ``LANG`` is read once,
when this module is imported (tests set the attribute instead).

Every sentence, label or chart string the Python layer builds comes from
``site/i18n/{en,tr}.yml`` through ``t(key, **fields)``. Templates are whole sentences
with named ``{fields}``; Plotly placeholders such as ``%{y:.2f}`` are left alone. A
Turkish entry may be the literal ``TODO`` while it waits for translation: ``t`` then
falls back to English, and ``deploy_problems()`` fails a deploy that includes Turkish.
"""
from __future__ import annotations

import math
import os
import re
import unicodedata
from collections.abc import Mapping, Sequence
from functools import lru_cache

import yaml

from hazelnut.site.config import SITE_DIR, SITE_URL

LANGS = ("en", "tr")
DEFAULT = "en"
I18N_DIR = SITE_DIR / "i18n"
TODO = "TODO"
# Comma-separated languages a build is deploying, e.g. "en,tr". When it names Turkish,
# a TODO entry left in tr.yml is an error (deploy_problems).
DEPLOY_FLAG = "SITE_DEPLOY"
MINUS = "−"  # typographic minus sign, used for negative changes in every language


def lang() -> str:
    """The active language: the first ``en``/``tr`` entry of ``QUARTO_PROFILE`` (a
    comma-separated list), else ``SITE_LANG``, else English."""
    for name in os.environ.get("QUARTO_PROFILE", "").split(","):
        if name.strip() in LANGS:
            return name.strip()
    site_lang = os.environ.get("SITE_LANG", "").strip()
    if not site_lang:
        return DEFAULT
    if site_lang not in LANGS:
        raise ValueError(f"SITE_LANG={site_lang!r}; expected one of {', '.join(LANGS)}")
    return site_lang


LANG = lang()


def site_url() -> str:
    """The active language's site root: ``SITE_URL`` for English, ``SITE_URL`` + ``tr/``
    for Turkish (the profiles' ``website.site-url``)."""
    return SITE_URL if LANG == DEFAULT else f"{SITE_URL}{LANG}/"


# --- strings ----------------------------------------------------------------------------

_FIELD = re.compile(r"\{(\w+)\}")


def _flatten(node: Mapping, prefix: str, out: dict[str, str], source: str) -> None:
    for key, value in node.items():
        if isinstance(key, bool) or not isinstance(key, (str, int)):
            raise ValueError(f"{source}: key {key!r} under {prefix or 'the top'} is not text "
                             "(quote it)")
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            _flatten(value, path + ".", out, source)
        elif isinstance(value, str):
            out[path] = value
        else:
            raise ValueError(f"{source}: {path} is {value!r}, not text (quote it)")


@lru_cache(maxsize=None)
def _load(code: str) -> dict[str, str]:
    path = I18N_DIR / f"{code}.yml"
    out: dict[str, str] = {}
    _flatten(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, "", out, path.name)
    return out


def strings(code: str) -> dict[str, str]:
    """Every string of language ``code`` as {dotted key: template}."""
    return _load(code)


def fields(template: str) -> set[str]:
    """The ``{field}`` names in a template (Plotly's ``%{x}`` counts; ``%{y:.2f}`` does
    not, it has a format)."""
    return set(_FIELD.findall(template))


def has(key: str) -> bool:
    return key in strings(DEFAULT)


def t(key: str, **values) -> str:
    """The active language's template for ``key`` with its ``{fields}`` filled in.

    A Turkish entry still marked ``TODO`` falls back to English. Placeholders not given
    in ``values`` (Plotly's ``%{x}``, ``%{text}``) are left as they are."""
    template = strings(LANG).get(key)
    if template is None or template == TODO:
        template = strings(DEFAULT).get(key)
        if template is None:
            raise KeyError(f"no string {key!r} in site/i18n/{DEFAULT}.yml")
    if not values:
        return template
    return _FIELD.sub(lambda m: str(values[m[1]]) if m[1] in values else m[0], template)


def crop_name(crop) -> str:
    """A crop's name in the active language (``crop.<slug>.name``), else ``crop.name``."""
    key = f"crop.{crop.slug}.name"
    return t(key) if has(key) else crop.name


def crop_country(crop) -> str:
    """A crop's country in the active language (``crop.<slug>.country``), else
    ``crop.country``."""
    key = f"crop.{crop.slug}.country"
    return t(key) if has(key) else crop.country


def country_key(name: str) -> str:
    """The ``country.<key>`` of a country name: folded to ASCII, lower case, every run of
    other characters as ``_`` ("Côte d'Ivoire" -> ``cote_d_ivoire``). A key passes
    through unchanged."""
    ascii_ = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_.lower()).strip("_")


def country_name(name: str) -> str:
    """An export destination's name in the active language, from its UN Comtrade name (or
    its ``country.<key>``). A name without an entry is returned as it is."""
    key = f"country.{country_key(name)}"
    return t(key) if has(key) else name


def crop_source_name(source: str) -> str:
    """A crop-estimate source key from the results ("national") in words, from
    ``crop_source.<key>``; a key without an entry is returned as it is."""
    key = f"crop_source.{source}"
    return t(key) if has(key) else source


# Turkish dotted and dotless i: Python's str.upper/lower map i -> I and İ -> i̇.
_TR_UPPER = {"i": "İ", "ı": "I"}
_TR_LOWER = {"İ": "i", "I": "ı"}


def upper_first(text: str) -> str:
    """``text`` with its first letter in upper case, by the active language's rules
    ("ikinci" -> "İkinci" in Turkish)."""
    if not text:
        return text
    first = text[0]
    if LANG == "tr" and first in _TR_UPPER:
        return _TR_UPPER[first] + text[1:]
    return first.upper() + text[1:]


def lower(text: str) -> str:
    """``text`` in lower case, by the active language's rules ("IĞDIR" -> "ığdır" in
    Turkish)."""
    if LANG == "tr":
        text = "".join(_TR_LOWER.get(c, c) for c in text)
    return text.lower()


def plural(key: str, n: int, **values) -> str:
    """``t(key.one)`` when ``n`` is 1, else ``t(key.other)``, with ``n`` filled in."""
    return t(f"{key}.one" if n == 1 else f"{key}.other", n=n, **values)


def join_names(names: Sequence[str]) -> str:
    """["A", "B", "C"] -> "A, B and C" in the active language."""
    names = [str(n) for n in names]
    if len(names) == 1:
        return names[0]
    return t("list.and", names=", ".join(names[:-1]), last=names[-1])


def parity_problems(en: Mapping[str, str], tr: Mapping[str, str]) -> list[str]:
    """Keys in only one language, and keys whose ``{field}`` sets differ. A Turkish
    ``TODO`` entry has no fields to compare yet."""
    problems = []
    for key in sorted(set(en) | set(tr)):
        if key not in tr:
            problems.append(f"{key}: missing in tr")
        elif key not in en:
            problems.append(f"{key}: not in en")
        elif tr[key] != TODO and fields(en[key]) != fields(tr[key]):
            show = lambda s: "{" + ", ".join(sorted(s)) + "}"  # noqa: E731
            problems.append(f"{key}: fields differ (en {show(fields(en[key]))}, "
                            f"tr {show(fields(tr[key]))})")
    return problems


def deploy_problems(tr: Mapping[str, str] | None = None,
                    deploying: Sequence[str] | None = None) -> list[str]:
    """Turkish entries still marked ``TODO``, when Turkish is among the languages being
    deployed: ``deploying``, else the ``SITE_DEPLOY`` variable ("en,tr"). Otherwise none."""
    if deploying is None:
        deploying = os.environ.get(DEPLOY_FLAG, "").split(",")
    if "tr" not in {s.strip() for s in deploying}:
        return []
    tr = strings("tr") if tr is None else tr
    return [f"{key}: not translated (TODO) in tr" for key, v in sorted(tr.items()) if v == TODO]


# --- formats ----------------------------------------------------------------------------

def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _na() -> str:
    return t("na")


def _local(s: str) -> str:
    """An English-formatted number ("1,234.5") with the active language's separators."""
    dec, thou = t("format.decimal"), t("format.thousands")
    if (dec, thou) == (".", ","):
        return s
    return "".join(dec if c == "." else thou if c == "," else c for c in s)


def fmt_number(x, dp: int = 2) -> str:
    """A number with thousands separators and ``dp`` decimals: ``1,234.50`` / ``1.234,50``."""
    return _na() if _missing(x) else _local(f"{x:,.{dp}f}")


def fmt_tonnes(x) -> str:
    """Whole tonnes with thousands separators: ``86,440`` / ``86.440``."""
    return _na() if _missing(x) else _local(f"{round(x):,}")


def fmt_usd(x, dp: int = 2) -> str:
    """US dollars: ``$4.13`` / ``4,13 $``."""
    return _na() if _missing(x) else t("format.usd", value=fmt_number(x, dp))


def _plain(v: float, dp: int) -> str:
    return _local(str(round(v)) if dp == 0 else f"{v:.{dp}f}")


def fmt_pct(x, dp: int = 0, *, signed: bool = False) -> str:
    """A fraction as a percent with ``dp`` decimals: ``31.5%`` / ``%31,5``.

    ``signed`` adds the sign: ``+31.5%``, ``−3.5%`` (``−%3,5``); a value that rounds to
    zero has none. Unsigned, a negative value takes ``format.pct_minus``: ``-3%`` in
    English, as its pages have always shown, ``−%3`` in Turkish."""
    if _missing(x):
        return _na()
    v = x * 100
    if signed:
        p = round(v, dp)
        if p == 0:
            return t("format.pct", value=_plain(0, dp))
        return t("format.pct_signed", sign="+" if p > 0 else MINUS, value=_plain(abs(p), dp))
    body = _plain(v, dp)
    if body.startswith("-"):
        return t("format.pct_signed", sign=t("format.pct_minus"), value=body[1:])
    return t("format.pct", value=body)


def fmt_signed(x, dp: int = 2) -> str:
    """A signed number with ``dp`` decimals: ``−0.10``, ``+0.18``; zero has no sign."""
    if _missing(x):
        return _na()
    v = round(x, dp)
    if v == 0:
        return _plain(0.0, dp)
    return ("+" if v > 0 else MINUS) + _plain(abs(v), dp)


def month_name(month: int, short: bool = False) -> str:
    """``10`` -> ``October`` / ``Ekim``; with ``short``, ``Oct`` / ``Eki``."""
    return t(f"{'month_short' if short else 'month'}.{int(month)}")


def _parse(as_of: str) -> tuple[int, int | None]:
    """``"2026-09"`` -> (2026, 9); a yearly ``"2026"`` -> (2026, None)."""
    year, _, month = str(as_of).partition("-")
    return int(year), (int(month) if month else None)


def month_label(as_of: str) -> str:
    """``"2026-10"`` -> ``"October 2026"`` / ``"Ekim 2026"``; a yearly ``"2026"`` stays."""
    year, month = _parse(as_of)
    return str(year) if month is None else t("format.month_year", month=month_name(month),
                                              year=year)


def as_of(manifest: Mapping) -> str:
    """"Data as of <Month YYYY> · refreshed weekly", plus the oldest stale source if any.

    A stale output with no date (it failed and had no earlier file) is "unavailable"."""
    month = month_label(manifest["as_of"])
    stale = [o.get("as_of") for o in manifest.get("outputs", {}).values() if o.get("stale")]
    dated = [a for a in stale if a]
    if dated:
        # A yearly as_of counts as the start of its year (month 0) when ordering.
        oldest = month_label(min(dated, key=lambda a: (_parse(a)[0], _parse(a)[1] or 0)))
        key = "stamp.stale_from_some_unavailable" if len(dated) < len(stale) else "stamp.stale_from"
        return t(key, month=month, oldest=oldest)
    if stale:
        return t("stamp.stale_unavailable", month=month)
    return t("stamp.fresh", month=month)


def plotly_locale() -> dict[str, str]:
    """The Plotly locale name and ``layout.separators`` (decimal, then thousands)."""
    return {"locale": LANG, "separators": t("format.decimal") + t("format.thousands")}

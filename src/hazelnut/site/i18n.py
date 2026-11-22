"""The site's active language (English or Turkish).

Quarto renders the site once per language profile (``site/_quarto-en.yml``,
``site/_quarto-tr.yml``; ``scripts/render_site.py`` runs both) and passes the active
profile to page cells as ``QUARTO_PROFILE``. Outside Quarto (tests, scripts) the
``SITE_LANG`` variable picks the language; English is the default.
"""
from __future__ import annotations

import os

LANGS = ("en", "tr")
DEFAULT = "en"


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

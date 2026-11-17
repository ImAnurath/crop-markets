"""Crop configuration for the portfolio site (read from site/crops.yml)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SITE_DIR = REPO_ROOT / "site"
CROPS_FILE = SITE_DIR / "crops.yml"
SITE_URL = "https://imanurath.github.io/crop-markets/"

_STR_KEYS = ("slug", "name", "country")
_LIST_KEYS = ("exchanges", "sections", "analyses", "range_currencies")


@dataclass(frozen=True)
class LocalCurrency:
    """The crop country's own currency: button label and its price column in the site data."""

    label: str
    column: str


@dataclass(frozen=True)
class CropConfig:
    slug: str
    name: str
    country: str
    exchanges: tuple[str, ...]
    sections: tuple[str, ...]
    analyses: tuple[str, ...]
    range_currencies: tuple[str, ...]
    local_currency: LocalCurrency


def load_crops(path: Path = CROPS_FILE) -> dict[str, CropConfig]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping of crop slug to settings")
    crops: dict[str, CropConfig] = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            raise ValueError(f"crop '{key}': expected a mapping")
        for k in _STR_KEYS + _LIST_KEYS + ("local_currency",):
            if k not in entry:
                raise ValueError(f"crop '{key}': missing key '{k}'")
        for k in _STR_KEYS:
            if not isinstance(entry[k], str):
                raise ValueError(f"crop '{key}': '{k}' must be a string")
        for k in _LIST_KEYS:
            if not isinstance(entry[k], list):
                raise ValueError(f"crop '{key}': '{k}' must be a list")
        local = entry["local_currency"]
        if not (
            isinstance(local, dict)
            and set(local) == {"label", "column"}
            and all(isinstance(v, str) and v for v in local.values())
        ):
            raise ValueError(
                f"crop '{key}': 'local_currency' must be a mapping with non-empty "
                "string 'label' and 'column'"
            )
        if entry["slug"] != key:
            raise ValueError(
                f"crop '{key}': slug '{entry['slug']}' does not match its key"
            )
        crops[key] = CropConfig(
            slug=entry["slug"],
            name=entry["name"],
            country=entry["country"],
            **{k: tuple(str(v) for v in entry[k]) for k in _LIST_KEYS},
            local_currency=LocalCurrency(label=local["label"], column=local["column"]),
        )
    return crops

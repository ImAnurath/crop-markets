"""The one crop registry: maps a crop slug to its data module."""
from __future__ import annotations

from types import ModuleType

from hazelnut.site import hazelnut_data

CROP_MODULES: dict[str, ModuleType] = {"hazelnut": hazelnut_data}


def crop_module(slug: str) -> ModuleType:
    try:
        return CROP_MODULES[slug]
    except KeyError:
        raise ValueError(f"unknown crop: {slug!r}") from None

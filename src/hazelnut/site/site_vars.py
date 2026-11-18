"""Deploy guard for the owner details in site/_variables.yml (byline, bio, profile links).

The weekly workflow runs ``scripts/check_site_vars.py`` before rendering, so a placeholder
("OWNER: fill in", "place holder", an empty value or a link that is not a URL) never goes live.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from hazelnut.site.config import SITE_DIR

VARIABLES_FILE = SITE_DIR / "_variables.yml"
PLACEHOLDER_MARKERS = ("fill in", "place holder", "placeholder")


def _value_problem(key: str, value) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return f"{key}: empty"
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.upper().startswith("OWNER:"):
        return f"{key}: still an owner placeholder ({text!r})"
    lowered = text.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker in lowered:
            return f"{key}: looks like a placeholder ({text!r})"
    if key.endswith("_url") and not lowered.startswith(("https://", "http://")):
        return f"{key}: not a URL ({text!r})"
    return None


def _walk(prefix: str, node, problems: list[str]) -> None:
    if isinstance(node, dict):
        if not node:
            problems.append(f"{prefix or 'file'}: empty")
        for k, v in node.items():
            _walk(f"{prefix}.{k}" if prefix else str(k), v, problems)
    elif isinstance(node, list):
        if not node:
            problems.append(f"{prefix}: empty")
        for i, v in enumerate(node):
            _walk(f"{prefix}[{i}]", v, problems)
    else:
        problem = _value_problem(prefix, node)
        if problem:
            problems.append(problem)


def check_site_vars(path: Path = VARIABLES_FILE) -> list[str]:
    """Problems with the owner details in ``path``; an empty list means it is fit to publish."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{path.name}: missing"]
    except (OSError, yaml.YAMLError) as e:
        return [f"{path.name}: unreadable ({e})"]
    if not isinstance(data, dict):
        return [f"{path.name}: expected a mapping of variable names to values"]
    problems: list[str] = []
    _walk("", data, problems)
    return problems

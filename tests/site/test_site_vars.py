"""The owner-details deploy guard, on temp files only (never the real site/_variables.yml)."""

import importlib.util
from pathlib import Path

import pytest

from hazelnut.site.site_vars import check_site_vars

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_site_vars.py"

GOOD = """\
# Owner details
author_name: "Jane Doe"
author_bio: "Data analyst working on commodity markets."
github_url: "https://github.com/janedoe"
linkedin_url: "https://www.linkedin.com/in/janedoe/"
"""


def _write(tmp_path, text):
    path = tmp_path / "_variables.yml"
    path.write_text(text, encoding="utf-8")
    return path


def _with(tmp_path, key, raw_value):
    lines = [f"{key}: {raw_value}" if line.startswith(f"{key}:") else line for line in GOOD.splitlines()]
    return _write(tmp_path, "\n".join(lines) + "\n")


def test_filled_in_file_passes(tmp_path):
    assert check_site_vars(_write(tmp_path, GOOD)) == []


def test_committed_template_fails_on_every_value(tmp_path):
    text = "\n".join(f'{k}: "OWNER: fill in"' for k in
                     ("author_name", "author_bio", "github_url", "linkedin_url"))
    problems = check_site_vars(_write(tmp_path, text))
    assert len(problems) == 4 and all("placeholder" in p for p in problems)


@pytest.mark.parametrize("key, raw, word", [
    ("author_name", '"OWNER: Jane Doe"', "placeholder"),
    ("author_name", '"owner: Jane Doe"', "placeholder"),
    ("author_bio", '"place holder"', "placeholder"),
    ("author_bio", '"Bio placeholder, to do"', "placeholder"),
    ("author_bio", '"Please FILL IN later"', "placeholder"),
    ("author_bio", '""', "empty"),
    ("author_bio", '"   "', "empty"),
    ("author_bio", "", "empty"),
    ("github_url", '"github.com/janedoe"', "not a URL"),
])
def test_placeholder_values_fail(tmp_path, key, raw, word):
    problems = check_site_vars(_with(tmp_path, key, raw))
    assert len(problems) == 1
    assert problems[0].startswith(f"{key}:") and word in problems[0]


def test_missing_empty_and_malformed_files_fail(tmp_path):
    assert check_site_vars(tmp_path / "nope.yml") == ["nope.yml: missing"]
    assert check_site_vars(_write(tmp_path, "# only a comment\n"))
    assert check_site_vars(_write(tmp_path, "author_name: [unclosed\n"))
    assert check_site_vars(_write(tmp_path, "- a list\n"))


def test_script_exit_codes(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("check_site_vars", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main([str(_write(tmp_path, GOOD))]) == 0
    assert mod.main([str(_with(tmp_path, "author_bio", '"place holder"'))]) == 1
    assert "PROBLEM: author_bio" in capsys.readouterr().out

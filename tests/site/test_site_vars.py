"""The owner-details deploy guard, on temp files only (never the real site/_variables.yml),
and the Turkish-strings check the same script runs (SITE_DEPLOY, i18n.deploy_problems)."""

import importlib.util
from pathlib import Path

import pytest

from hazelnut.site import i18n
from hazelnut.site.site_vars import REQUIRED_KEYS, check_site_vars

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_site_vars.py"

GOOD = """\
# Owner details
author_name: "Jane Doe"
author_bio: "Data analyst working on commodity markets."
author_bio_tr: "Emtia piyasaları üzerine çalışan veri analisti."
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
    text = "\n".join(f'{k}: "OWNER: fill in"' for k in REQUIRED_KEYS)
    problems = check_site_vars(_write(tmp_path, text))
    assert len(problems) == 5 and all("placeholder" in p for p in problems)


def test_every_owner_detail_the_pages_use_is_required():
    # The Turkish byline (site/hazelnut/index.qmd) uses author_bio_tr.
    assert REQUIRED_KEYS == ("author_name", "author_bio", "author_bio_tr", "github_url",
                             "linkedin_url")


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_a_missing_owner_detail_fails(tmp_path, key):
    text = "".join(line + "\n" for line in GOOD.splitlines() if not line.startswith(f"{key}:"))
    assert check_site_vars(_write(tmp_path, text)) == [f"{key}: missing"]


@pytest.mark.parametrize("key, raw, word", [
    ("author_name", '"OWNER: Jane Doe"', "placeholder"),
    ("author_name", '"owner: Jane Doe"', "placeholder"),
    ("author_bio", '"place holder"', "placeholder"),
    ("author_bio", '"Bio placeholder, to do"', "placeholder"),
    ("author_bio", '"Please FILL IN later"', "placeholder"),
    ("author_bio", '""', "empty"),
    ("author_bio", '"   "', "empty"),
    ("author_bio", "", "empty"),
    ("author_bio_tr", '"OWNER: Türkçe tanıtım"', "placeholder"),
    ("author_bio_tr", '""', "empty"),
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


def _script():
    spec = importlib.util.spec_from_file_location("check_site_vars", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_exit_codes(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(i18n.DEPLOY_FLAG, raising=False)
    mod = _script()
    assert mod.main([str(_write(tmp_path, GOOD))]) == 0
    assert mod.main([str(_with(tmp_path, "author_bio", '"place holder"'))]) == 1
    assert "PROBLEM: author_bio" in capsys.readouterr().out


def test_script_fails_a_turkish_deploy_on_a_todo_entry(tmp_path, capsys, monkeypatch):
    # The workflow sets SITE_DEPLOY=en,tr, so a "TODO" left in tr.yml stops it before deploy.
    monkeypatch.setattr(i18n, "strings", lambda code: {"a": "A", "b": i18n.TODO})
    good = str(_write(tmp_path, GOOD))
    mod = _script()

    monkeypatch.delenv(i18n.DEPLOY_FLAG, raising=False)
    assert mod.main([good]) == 0
    monkeypatch.setenv(i18n.DEPLOY_FLAG, "en")
    assert mod.main([good]) == 0
    capsys.readouterr()

    monkeypatch.setenv(i18n.DEPLOY_FLAG, "en,tr")
    assert mod.main([good]) == 1
    out = capsys.readouterr().out
    assert "PROBLEM: b: not translated (TODO) in tr" in out
    assert "PROBLEM: a" not in out


def test_script_passes_a_turkish_deploy_without_todo_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "strings", lambda code: {"a": "A", "b": "B"})
    monkeypatch.setenv(i18n.DEPLOY_FLAG, "en,tr")
    assert _script().main([str(_write(tmp_path, GOOD))]) == 0


def test_script_fails_on_a_file_without_the_turkish_bio(tmp_path, capsys, monkeypatch):
    # The owner's file before author_bio_tr is added: everything else filled in.
    monkeypatch.delenv(i18n.DEPLOY_FLAG, raising=False)
    text = "".join(line + "\n" for line in GOOD.splitlines() if not line.startswith("author_bio_tr:"))
    assert _script().main([str(_write(tmp_path, text))]) == 1
    out = capsys.readouterr().out
    assert "PROBLEM: author_bio_tr: missing" in out.splitlines()

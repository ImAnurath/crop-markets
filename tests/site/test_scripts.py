import importlib.util
import json
from pathlib import Path

import pytest

from hazelnut.forecast.dataset import _FILES
from hazelnut.forecast.dataset import NATIONAL_CROP_FILE
from hazelnut.site.site_data import ORDU_FILE

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def build_site_data():
    return _load("build_site_data")


@pytest.fixture
def build_workbook():
    return _load("build_workbook")


@pytest.fixture
def dirs(tiny_tables, tmp_path):
    interim, manual = tmp_path / "interim", tmp_path / "manual"
    interim.mkdir()
    manual.mkdir()
    for key, name in _FILES.items():
        tiny_tables[key].to_csv(interim / name, index=False)
    tiny_tables["ordu_daily"].to_csv(interim / ORDU_FILE, index=False)
    tiny_tables["national_crop"].to_csv(manual / NATIONAL_CROP_FILE, index=False)
    return interim, manual, tmp_path / "out", tmp_path / "backtest"


def _argv(dirs, *extra):
    interim, manual, out, backtest = dirs
    return ["--interim", str(interim), "--manual", str(manual), "--out", str(out),
            "--backtest", str(backtest), "--today", "2008-02-15", *extra]


def test_build_site_data_exit_zero_on_good_input(build_site_data, dirs, capsys):
    assert build_site_data.main(_argv(dirs)) == 0
    out = dirs[2] / "hazelnut"
    assert json.loads((out / "manifest.json").read_text())["crop"] == "hazelnut"
    printed = capsys.readouterr().out
    assert "prices_monthly: fresh" in printed
    assert "stale" not in printed and "missing" not in printed


def test_build_site_data_exit_one_on_core_failure(build_site_data, dirs, capsys):
    for f in dirs[0].glob("*.csv"):
        f.unlink()
    assert build_site_data.main(_argv(dirs)) == 1
    assert "core outputs failed" in capsys.readouterr().out


def test_build_site_data_exit_one_on_validation_problem(build_site_data, dirs, capsys):
    argv = _argv(dirs)
    argv[argv.index("--today") + 1] = "2012-01-01"  # data far too old
    assert build_site_data.main(argv) == 1


def test_step_summary_written_when_env_set(build_site_data, dirs, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert build_site_data.main(_argv(dirs)) == 0
    text = summary.read_text(encoding="utf-8")
    assert "| output | status |" in text
    assert "prices_monthly" in text


def test_no_summary_without_env(build_site_data, dirs, tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert build_site_data.main(_argv(dirs)) == 0


def test_build_workbook_writes_xlsx(build_site_data, build_workbook, dirs, tmp_path):
    build_site_data.main(_argv(dirs))
    out_file = tmp_path / "dl" / "hazelnut-market-data.xlsx"
    rc = build_workbook.main(["--data", str(dirs[2]), "--out", str(tmp_path / "dl")])
    assert rc == 0 and out_file.exists()


def test_build_workbook_unknown_crop(build_workbook, tmp_path):
    assert build_workbook.main(["--crop", "nope", "--data", str(tmp_path), "--out", str(tmp_path)]) == 1


def test_results_written_under_results_subfolder(build_site_data, dirs):
    real = SCRIPTS.parent / "reports" / "backtest"  # tracked in git, read-only here
    argv = _argv(dirs)
    argv[argv.index("--backtest") + 1] = str(real)
    assert build_site_data.main(argv) == 0
    assert (dirs[2] / "hazelnut" / "results" / "scoreboard_dev.csv").exists()
    assert not (dirs[2] / "hazelnut" / "scoreboard_dev.csv").exists()

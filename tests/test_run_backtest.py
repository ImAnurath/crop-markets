import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_backtest.py"
spec = importlib.util.spec_from_file_location("run_backtest", SCRIPT)
run_backtest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_backtest)


def test_holdout_guard(tmp_path, capsys):
    path = tmp_path / "naive.csv"
    run_backtest.check_holdout_guard(path, force=False)  # no file: fine
    path.write_text("x\n")
    with pytest.raises(SystemExit) as exc:
        run_backtest.check_holdout_guard(path, force=False)
    assert exc.value.code == 1
    assert "holdout already scored for naive" in capsys.readouterr().err
    run_backtest.check_holdout_guard(path, force=True)  # forced: fine

from datetime import datetime, timezone

import pandas as pd
import pytest
from openpyxl import load_workbook

from hazelnut.site.config import CropConfig
from hazelnut.site.site_data import write_site_data
from hazelnut.site.workbook import build_workbook

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
CROP = CropConfig("hazelnut", "Hazelnut", "Turkey", (), (), (), ("usd",))
URL = "https://example.org/crop-markets/"
SHEETS = ["README", "Prices", "Ordu", "Exports", "Top destinations", "Crop",
          "Forecast range", "Scoreboard", "Sources"]


def _results(data_dir):
    res = data_dir / "results"
    res.mkdir(parents=True, exist_ok=True)
    board = pd.DataFrame({"method": ["naive", "sarima", "chronos"], "horizon": [1, 1, 1],
                          "n": [10, 10, 10], "mae": [0.3, 0.2, 0.25], "ratio": [1.0, 0.67, 0.83]})
    board.to_csv(res / "scoreboard_dev.csv", index=False)
    board.assign(note="scored once, never tuned on").to_csv(res / "scoreboard_holdout.csv", index=False)


@pytest.fixture
def data_dir(tiny_tables, tmp_path):
    d = tmp_path / "data"
    write_site_data(CROP, tiny_tables, d, NOW)
    _results(d)
    return d


def _wb(data_dir, tmp_path):
    out = build_workbook(data_dir, tmp_path / "x.xlsx", CROP, URL)
    return load_workbook(out)


def test_sheet_order(data_dir, tmp_path):
    assert _wb(data_dir, tmp_path).sheetnames == SHEETS


def test_headers_frozen_and_bold(data_dir, tmp_path):
    wb = _wb(data_dir, tmp_path)
    for name in ("Prices", "Exports", "Top destinations", "Crop", "Forecast range", "Scoreboard"):
        ws = wb[name]
        assert ws.freeze_panes == "A2"
        assert ws["A1"].font.bold
    p = wb["Prices"]
    assert "USD/kg" in [c.value for c in p[1]]
    assert p.max_row > 2


def test_readme_has_url_and_as_of(data_dir, tmp_path):
    ws = _wb(data_dir, tmp_path)["README"]
    text = "\n".join(str(c.value) for r in ws.iter_rows() for c in r if c.value)
    assert ws["A1"].value == "Hazelnut market data (Turkey)"
    assert URL in text and "December 2007" in text
    assert "Prices" in text and "Scoreboard" in text


def test_scoreboard_has_holdout_label_and_readable_names(data_dir, tmp_path):
    ws = _wb(data_dir, tmp_path)["Scoreboard"]
    text = "\n".join(str(c.value) for r in ws.iter_rows() for c in r if c.value)
    assert "scored once, never tuned on" in text
    assert "Chronos-Bolt" in text and "SARIMA" in text
    assert "chronos" not in [c.value for r in ws.iter_rows() for c in r]


def test_sources_lists_all_providers(data_dir, tmp_path):
    ws = _wb(data_dir, tmp_path)["Sources"]
    text = "\n".join(str(c.value) for r in ws.iter_rows() for c in r if c.value)
    for p in ("UN Comtrade", "FAOSTAT", "TOBB", "Giresun", "Ordu", "Open-Meteo", "ECB", "OECD"):
        assert p in text
    assert "CC BY 4.0" in text


def test_missing_output_gives_placeholder_sheet(tiny_tables, tmp_path):
    d = tmp_path / "data"
    partial = {k: v for k, v in tiny_tables.items() if k != "comtrade"}
    write_site_data(CROP, partial, d, NOW)
    wb = _wb(d, tmp_path)
    assert wb.sheetnames == SHEETS
    assert wb["Top destinations"]["A1"].value == "Not available in this refresh."
    assert wb["Scoreboard"]["A1"].value == "Not available in this refresh."
    assert wb["Prices"]["A1"].value != "Not available in this refresh."
    readme = "\n".join(str(c.value) for r in wb["README"].iter_rows() for c in r if c.value)
    assert "exports_top" in readme or "Top destinations" in readme


def test_stale_output_listed_in_readme(tiny_tables, tmp_path):
    d = tmp_path / "data"
    write_site_data(CROP, tiny_tables, d, NOW)
    partial = {k: v for k, v in tiny_tables.items() if k != "comtrade"}
    write_site_data(CROP, partial, d, NOW)
    wb = _wb(d, tmp_path)
    assert wb["Top destinations"].max_row > 1
    readme = "\n".join(str(c.value) for r in wb["README"].iter_rows() for c in r if c.value)
    assert "stale" in readme.lower() and "December 2007" in readme

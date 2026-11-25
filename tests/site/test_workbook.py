from datetime import datetime, timezone

import pandas as pd
import pytest
from openpyxl import load_workbook

from hazelnut.site.config import CropConfig, LocalCurrency
from hazelnut.site.site_data import write_site_data
from hazelnut.site.workbook import build_workbook

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
CROP = CropConfig(
    "hazelnut", "Hazelnut", "Turkey", (), (), (), ("usd",), LocalCurrency("TL", "try_kg")
)
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
    assert "Top destinations" in readme and "(not available in this refresh)" in readme


def test_stale_output_listed_in_readme(tiny_tables, tmp_path):
    d = tmp_path / "data"
    write_site_data(CROP, tiny_tables, d, NOW)
    partial = {k: v for k, v in tiny_tables.items() if k != "comtrade"}
    write_site_data(CROP, partial, d, NOW)
    wb = _wb(d, tmp_path)
    assert wb["Top destinations"].max_row > 1
    readme = "\n".join(str(c.value) for r in wb["README"].iter_rows() for c in r if c.value)
    assert "stale, as of December 2007" in readme
    assert "exports_top" not in readme


# --- the English workbook stays as it was; the Turkish one mirrors it -------------------

import hashlib  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from hazelnut.site import i18n  # noqa: E402
from hazelnut.site.workbook import workbook_filename  # noqa: E402

EN_SNAPSHOT = Path(__file__).parent / "fixtures" / "workbook_en.json"
TR_SHEETS = ["Açıklama", "Fiyatlar", "Ordu", "İhracat", "Başlıca pazarlar", "Rekolte",
             "Tahmin aralığı", "Puan tablosu", "Kaynaklar"]


def workbook_digest(path) -> dict:
    """Each sheet's header row, row count and a hash of every cell value, in sheet order:
    enough to show two builds wrote the same workbook."""
    wb = load_workbook(path)
    out = {}
    for ws in wb.worksheets:
        cells = [[c.value for c in row] for row in ws.iter_rows()]
        blob = json.dumps(cells, default=str, ensure_ascii=False).encode("utf-8")
        out[ws.title] = {"header": [v for v in (cells[0] if cells else []) if v is not None],
                         "rows": ws.max_row, "sha256": hashlib.sha256(blob).hexdigest()}
    return out


def test_english_workbook_is_unchanged(data_dir, tmp_path):
    # Snapshot of the English build before the Turkish workbook existed (sheet names,
    # headers, every cell); it changes only for a deliberate English change.
    want = json.loads(EN_SNAPSHOT.read_text(encoding="utf-8"))
    assert workbook_digest(build_workbook(data_dir, tmp_path / "x.xlsx", CROP, URL)) == want


@pytest.fixture
def turkish_crop(turkish):
    """Turkish, with the crop module re-read in Turkish (it reads its words on import)."""
    from hazelnut.site import hazelnut_data

    importlib.reload(hazelnut_data)
    yield
    i18n.LANG = "en"
    importlib.reload(hazelnut_data)


def _tr_wb(data_dir, tmp_path):
    out = build_workbook(data_dir, tmp_path / "tr.xlsx", CROP, i18n.site_url())
    return load_workbook(out)


def test_turkish_workbook_has_turkish_sheet_names(turkish_crop, data_dir, tmp_path):
    names = _tr_wb(data_dir, tmp_path).sheetnames
    assert names == TR_SHEETS
    for name in names:  # Excel's rules for a sheet name
        assert len(name) <= 31 and not set(name) & set("[]:*?/\\"), name


def test_turkish_workbook_has_turkish_headers_and_readme(turkish_crop, data_dir, tmp_path):
    wb = _tr_wb(data_dir, tmp_path)
    assert [c.value for c in wb["Fiyatlar"][1]] == ["Ay", "Sezon", "USD/kg", "TL/kg",
                                                    "USD/TL kuru"]
    assert [c.value for c in wb["Puan tablosu"][1]][:2] == ["Yöntem", "Ufuk (ay)"]
    assert [c.value for c in wb["Kaynaklar"][1]] == ["Sağlayıcı", "Kullandığımız veri",
                                                     "Adres", "Atıf ve koşullar"]
    readme = wb["Açıklama"]
    assert readme["A1"].value == "Fındık piyasa verileri (Türkiye)"
    assert readme["A2"].value == "Veriler Aralık 2007 itibarıyla"
    assert readme["A3"].value == "https://imanurath.github.io/crop-markets/tr/"
    text = "\n".join(str(c.value) for r in readme.iter_rows() for c in r if c.value)
    assert "Fiyatlar" in text and "Puan tablosu" in text and "Prices" not in text


def test_turkish_workbook_holds_the_same_rows_as_the_english_one(data_dir, tmp_path, turkish):
    from hazelnut.site import hazelnut_data

    i18n.LANG = "en"
    en = load_workbook(build_workbook(data_dir, tmp_path / "en.xlsx", CROP, URL))
    i18n.LANG = "tr"
    importlib.reload(hazelnut_data)
    try:
        tr = _tr_wb(data_dir, tmp_path)
    finally:
        i18n.LANG = "en"
        importlib.reload(hazelnut_data)
    assert len(en.worksheets) == len(tr.worksheets)
    for e, t_ in zip(en.worksheets, tr.worksheets):
        assert (e.max_row, e.max_column) == (t_.max_row, t_.max_column), e.title
        if e.title in ("README", "Sources"):
            continue
        # Numbers (and their formats) are the same; only the words differ.
        for er, tr_row in zip(e.iter_rows(min_row=2), t_.iter_rows(min_row=2)):
            for a, b in zip(er, tr_row):
                if isinstance(a.value, (int, float)):
                    assert (a.value, a.number_format) == (b.value, b.number_format)


def test_workbook_filename_per_language(turkish):
    assert workbook_filename("hazelnut", "en") == "hazelnut-market-data.xlsx"
    assert workbook_filename("hazelnut", "tr") == "hazelnut-market-data-tr.xlsx"
    assert workbook_filename("hazelnut") == "hazelnut-market-data-tr.xlsx"  # active language
    for lang in i18n.LANGS:
        assert workbook_filename("rye", lang).isascii()


def test_site_url_per_language(turkish):
    assert i18n.site_url() == "https://imanurath.github.io/crop-markets/tr/"
    i18n.LANG = "en"
    assert i18n.site_url() == "https://imanurath.github.io/crop-markets/"

"""fetch_raw's Comtrade retry loop, with a mocked session (never touches the network)."""

import importlib.util
from pathlib import Path

import pytest
import requests

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_raw.py"


@pytest.fixture
def fetch_raw(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("fetch_raw", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "partner_areas.json").write_text("{}")
    monkeypatch.setattr(mod, "out_dir", lambda source: tmp_path)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    return mod


def _response(status: int, body: bytes) -> requests.Response:
    r = requests.Response()
    r.status_code, r._content, r.url = status, body, "https://comtradeapi.un.org/x"
    return r


def _serve(mod, monkeypatch, responses):
    calls = []

    def get(url, timeout=None):
        calls.append(url)
        return responses[min(len(calls), len(responses)) - 1]

    monkeypatch.setattr(mod.SESSION, "get", get)
    return calls


def _this_month(mod) -> str:
    return f"{mod.TODAY.year}-{mod.TODAY.month:02d}"


def test_comtrade_raises_after_rate_limit_retries_and_writes_nothing(fetch_raw, tmp_path, monkeypatch):
    calls = _serve(fetch_raw, monkeypatch, [_response(429, b'{"statusCode": 429}')])
    with pytest.raises(requests.HTTPError):
        fetch_raw.fetch_comtrade(start=_this_month(fetch_raw))
    assert len(calls) == 5
    assert sorted(p.name for p in tmp_path.iterdir()) == ["partner_areas.json"]


def test_comtrade_saves_month_after_a_rate_limited_retry(fetch_raw, tmp_path, monkeypatch):
    calls = _serve(fetch_raw, monkeypatch,
                   [_response(429, b"{}"), _response(200, b'{"count": 1, "data": [{"x": 1}]}')])
    fetch_raw.fetch_comtrade(start=_this_month(fetch_raw))
    assert len(calls) == 2
    period = _this_month(fetch_raw).replace("-", "")
    assert '"count": 1' in (tmp_path / f"{period}.json").read_text(encoding="utf-8")

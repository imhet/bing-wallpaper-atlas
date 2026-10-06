import json
from pathlib import Path

import pytest

from crawler.bing_api import BingApiError, fetch_market

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "hp_archive_zh_cn.json").read_text("utf-8"))


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_normalize_fields(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    session = FakeSession([FakeResponse(FIXTURE)])
    records = fetch_market("zh-cn", session=session)
    assert len(records) == 3
    first = records[0]
    assert first == {
        "market": "zh-cn",
        "date": "2026-10-05",
        "urlbase": "/th?id=OHR.DanxiaLandform_ZH-CN2386060246",
        "title": "条纹中的地球故事",
        "desc": "丹霞地貌，张掖国家地质公园，甘肃省，中国 (© Weiquan Lin/Getty Images)",
        "copyrightlink": FIXTURE["images"][0]["copyrightlink"],
        "quiz": FIXTURE["images"][0]["quiz"],
    }


def test_market_param_sent(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    session = FakeSession([FakeResponse({"images": []})])
    fetch_market("ja-jp", session=session)
    assert session.calls[0]["params"]["mkt"] == "ja-JP"


def test_empty_images_ok(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    session = FakeSession([FakeResponse({"images": []})])
    assert fetch_market("zh-cn", session=session) == []


def test_retries_then_raises(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    session = FakeSession([RuntimeError("boom")] * 3)
    with pytest.raises(BingApiError):
        fetch_market("zh-cn", session=session, max_retries=3)


def test_bad_record_skipped_not_fatal(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    bad = dict(FIXTURE["images"][0])
    bad["startdate"] = "202610"  # 坏日期
    payload = {"images": [bad, FIXTURE["images"][1]]}
    session = FakeSession([FakeResponse(payload)])
    records = fetch_market("zh-cn", session=session)
    assert [r["date"] for r in records] == ["2026-10-04"]  # 坏记录跳过，好记录保留

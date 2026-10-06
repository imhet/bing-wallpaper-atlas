import base64
import json
from pathlib import Path

from crawler.sources.bing_api_source import BingApiSource
from crawler.sources.niumoo_source import NiumooSource

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "niumoo_images.json").read_text("utf-8"))


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, timeout=None):
        return FakeResponse(self.payload)


def test_niumoo_fetch_normalizes():
    session = FakeSession(FIXTURE)
    records = NiumooSource().fetch(session=session)
    # 5 条原始数据：Danxia/Adelie/Edinburgh 保留，GrizzlySwim 归一化后与 Danxia 同日去重，2099 未来条目丢弃
    assert len(records) == 3
    first = records[0]
    assert first["market"] == "zh-cn"
    assert first["date"] == "2026-10-05"  # 2026-10-06 - 1 天，对齐 Bing startdate（真实配对实证）
    assert first["urlbase"] == "/th?id=OHR.DanxiaLandform_ZH-CN2386060246"
    assert first["title"] is None and first["copyrightlink"] is None
    assert "丹霞地貌" in first["desc"]
    assert [r["date"] for r in records] == ["2026-10-05", "2026-10-04", "2024-10-30"]


def test_niumoo_accepts_github_api_base64(monkeypatch):
    wrapped = {"content": base64.b64encode(json.dumps(FIXTURE).encode()).decode()}
    session = FakeSession(wrapped)
    records = NiumooSource().fetch(session=session)
    assert len(records) == 3


def test_niumoo_skips_bad_urls():
    bad = [{"date": "2024-01-01", "region": "zh-cn", "url": "https://example.com/nope.jpg", "desc": "x"}]
    records = NiumooSource().fetch(session=FakeSession(bad))
    assert records == []


def test_bing_api_source_covers_all_markets(monkeypatch):
    seen = []
    monkeypatch.setattr("crawler.sources.bing_api_source.fetch_market",
                        lambda market, idx=0, n=8: (seen.append(market), [{"market": market, "date": "2026-10-06", "urlbase": "/th?id=OHR.X_XX-XX1", "title": None, "desc": "", "copyrightlink": None, "quiz": None}])[1])
    records = BingApiSource().fetch()
    assert set(seen) == {"zh-cn", "en-us", "ja-jp", "en-gb", "de-de", "fr-fr", "ko-kr", "zh-tw"}
    assert len(records) == 8

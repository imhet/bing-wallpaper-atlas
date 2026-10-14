import base64
import json
from pathlib import Path

from crawler.sources.bing_api_source import BingApiSource
from crawler.sources.niumoo_source import NiumooSource
from crawler.sources.npanuhin_source import NpanuhinSource

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


def test_niumoo_one_bad_item_does_not_kill_source():
    # 一条缺 region/坏结构的条目只能丢自己，绝不能让整个 1341 条的历史源报废
    payload = [
        {"date": "2026-10-06", "region": "zh-cn", "url": "https://cn.bing.com/th?id=OHR.Good_ZH-CN1111111111_UHD.jpg", "desc": "ok"},
        {"date": "2026-10-05", "url": "https://cn.bing.com/th?id=OHR.NoRegion_ZH-CN2222222222_UHD.jpg", "desc": "缺 region"},
        {"date": "2026-10-04", "region": None, "url": "https://cn.bing.com/th?id=OHR.NullRegion_ZH-CN3333333333_UHD.jpg", "desc": "region 为 null"},
        {"date": "2026-10-03", "region": "", "url": "https://cn.bing.com/th?id=OHR.EmptyRegion_ZH-CN4444444444_UHD.jpg", "desc": "region 为空串"},
        {"date": "2026-10-02", "region": "zh-cn", "url": "https://cn.bing.com/th?id=OHR.Good2_ZH-CN5555555555_UHD.jpg", "desc": "ok2"},
    ]
    records = NiumooSource().fetch(session=FakeSession(payload))
    assert [r["urlbase"] for r in records] == [
        "/th?id=OHR.Good_ZH-CN1111111111",
        "/th?id=OHR.Good2_ZH-CN5555555555",
    ]


NPANUHIN_FIXTURE = [
    {
        "title": "Glade Creek Grist Mill, West Virginia, United States",
        "caption": None, "subtitle": None,
        "copyright": "© dszc/Getty Images",
        "description": "Glade Creek Grist Mill sits above the rocky waters of Glade Creek.",
        "date": "2011-06-01", "bing_url": None,
        "url": "https://bing.npanuhin.me/US/en/2011-06-01.jpg",
    },
    {
        "title": "Title-only record",
        "caption": None, "subtitle": None, "copyright": None,
        "description": None, "date": "2012-03-05", "bing_url": None,
        "url": "https://bing.npanuhin.me/US/en/2012-03-05.jpg",
    },
]


def test_npanuhin_fetch_maps_fields():
    records = NpanuhinSource().fetch(session=FakeSession(NPANUHIN_FIXTURE))
    assert len(records) == 2
    first = records[0]
    assert first["market"] == "en-us"  # US-en → en-us
    assert first["date"] == "2011-06-01"  # 归档已是规范日期，不做 niumoo 式 -1 平移
    assert first["urlbase"] == "https://bing.npanuhin.me/US/en/2011-06-01.jpg"  # 镜像绝对 URL 原样
    assert first["title"].startswith("Glade Creek")
    assert "Glade Creek" in first["desc"]
    assert first["copyright"] == "© dszc/Getty Images"  # build_record 用它补空解析摄影师/图库
    assert first["copyrightlink"] is None and first["quiz"] is None


def test_npanuhin_null_fields_normalized():
    records = NpanuhinSource().fetch(session=FakeSession(NPANUHIN_FIXTURE))
    only_title = records[1]
    assert only_title["desc"] == ""  # description null → 空串（schema desc 不可空）
    assert only_title["copyright"] is None


def test_npanuhin_drops_bad_items():
    payload = [
        {"title": "no date", "url": "https://bing.npanuhin.me/US/en/x.jpg"},
        {"title": "bad date", "date": "01/06/2012", "url": "https://bing.npanuhin.me/US/en/bad.jpg"},
        {"title": "no url", "date": "2012-02-01"},
        {"title": "relative url", "date": "2012-03-01", "url": "/US/en/rel.jpg"},
        {"title": "future", "date": "2999-01-01", "url": "https://bing.npanuhin.me/US/en/future.jpg"},
        # ≥ niumoo en-us 起点（2021-02）的重叠段丢弃：避免与既有记录在 upsert 整条替换下互相覆盖
        {"title": "overlap", "date": "2021-06-01", "url": "https://bing.npanuhin.me/US/en/2021-06-01.jpg"},
        {"title": "ok", "date": "2012-02-02", "url": "https://bing.npanuhin.me/US/en/2012-02-02.jpg"},
    ]
    records = NpanuhinSource().fetch(session=FakeSession(payload))
    assert [r["date"] for r in records] == ["2012-02-02"]


def test_npanuhin_dedupes_same_date():
    payload = [
        {"title": "first", "date": "2013-05-05", "url": "https://bing.npanuhin.me/US/en/2013-05-05.jpg"},
        {"title": "second", "date": "2013-05-05", "url": "https://bing.npanuhin.me/US/en/2013-05-05.jpg"},
    ]
    records = NpanuhinSource().fetch(session=FakeSession(payload))
    assert len(records) == 1 and records[0]["title"] == "first"


def test_npanuhin_normalizes_trailing_copyright():
    payload = [{"title": "t", "date": "2014-04-04", "copyright": "McPHOTO/age fotostock ©",
                "url": "https://bing.npanuhin.me/US/en/2014-04-04.jpg"}]
    records = NpanuhinSource().fetch(session=FakeSession(payload))
    assert records[0]["copyright"] == "© McPHOTO/age fotostock"  # 尾部 © 归一到头部，兼容版权解析器


def test_npanuhin_market_variants():
    # 其他市场接入（ja-jp 等 2024-04 起归档）：slug 按市场推导、end_date 参数化挡住与本地增量重叠段
    src = NpanuhinSource(market="ja-jp", end_date="2026-09-29")
    assert src.slug == "JP-ja"
    assert src.url.endswith("/JP-ja.json")
    payload = [
        {"title": "keep", "date": "2025-06-01", "url": "https://bing.npanuhin.me/JP/ja/2025-06-01.jpg"},
        {"title": "overlap", "date": "2026-09-29", "url": "https://bing.npanuhin.me/JP/ja/2026-09-29.jpg"},
    ]
    records = src.fetch(session=FakeSession(payload))
    assert [r["date"] for r in records] == ["2025-06-01"]
    assert records[0]["market"] == "ja-jp"


def test_npanuhin_default_is_en_us_deep_history():
    # 无参构造保持既有行为：US-en 深史、END_DATE 挡 niumoo 重叠段
    src = NpanuhinSource()
    assert src.slug == "US-en"
    assert src.market == "en-us"
    assert src.end_date == "2021-02-01"


def test_bing_api_source_covers_all_markets(monkeypatch):
    seen = []
    monkeypatch.setattr("crawler.sources.bing_api_source.fetch_market",
                        lambda market, idx=0, n=8: (seen.append(market), [{"market": market, "date": "2026-10-06", "urlbase": "/th?id=OHR.X_XX-XX1", "title": None, "desc": "", "copyrightlink": None, "quiz": None}])[1])
    records = BingApiSource().fetch()
    assert set(seen) == {"zh-cn", "en-us", "ja-jp", "en-gb", "de-de", "fr-fr", "ko-kr", "zh-tw"}
    assert len(records) == 8


def test_bing_api_source_one_failed_market_does_not_kill_source(monkeypatch):
    # 单市场失败只丢该市场，绝不能让整源报废（backfill 会把整源异常当源故障跳过）
    def flaky(market, idx=0, n=8):
        if market == "de-de":
            raise RuntimeError("api down")
        return [{"market": market, "date": "2026-10-06", "urlbase": "/th?id=OHR.X_XX-XX1",
                 "title": None, "desc": "", "copyrightlink": None, "quiz": None}]

    monkeypatch.setattr("crawler.sources.bing_api_source.fetch_market", flaky)
    records = BingApiSource().fetch()
    assert len(records) == 7
    assert all(r["market"] != "de-de" for r in records)

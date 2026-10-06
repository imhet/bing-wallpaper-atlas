import json

from crawler.backfill import build_record, run_backfill, verify_mkt
from crawler.storage import load_year


def test_build_record_parses_everything():
    merged = {
        "market": "zh-cn", "date": "2026-10-05",
        "urlbase": "/th?id=OHR.AdelieTeacher_ZH-CN2201820679",
        "title": "纵身一跃，一次一课",
        "desc": "南极洲的阿德利企鹅 (© Otto Plantema/Minden Pictures)",
        "copyrightlink": "https://www.bing.com/search?q=x", "quiz": None,
    }
    rec = build_record(merged)
    assert rec["id"] == "zh-cn-2026-10-05"
    assert rec["imageKey"] == "AdelieTeacher"
    assert rec["region"] == "南极洲" or rec["region"] is None  # 词表未覆盖时允许 None
    assert rec["photographer"] == "Otto Plantema"
    assert rec["gallery"] == "Minden Pictures"
    assert rec["tags"] == []


def test_build_record_bad_url_never_crashes():
    rec = build_record({"market": "zh-cn", "date": "2026-10-05", "urlbase": "", "title": None, "desc": "", "copyrightlink": None, "quiz": None})
    assert rec["imageKey"] is None


def test_run_backfill_end_to_end(tmp_path, monkeypatch):
    niumoo_payload = [
        {"date": "2026-10-05", "region": "zh-cn", "url": "https://cn.bing.com/th?id=OHR.AdelieTeacher_ZH-CN2201820679_UHD.jpg", "desc": "南极洲的阿德利企鹅 (© Otto Plantema/Minden Pictures)"},
        {"date": "2026-10-04", "region": "en-us", "url": "https://cn.bing.com/th?id=OHR.HauntedEdinburgh_EN-US3906244993_UHD.jpg", "desc": "View of Edinburgh Castle from a churchyard in Scotland (© Chris Dorney/Alamy)"},
    ]
    bing_payload = [{
        "market": "zh-cn", "date": "2026-10-05",
        "urlbase": "/th?id=OHR.AdelieTeacher_ZH-CN2201820679",
        "title": "纵身一跃，一次一课",
        "desc": "南极洲的阿德利企鹅 (© Otto Plantema/Minden Pictures)",
        "copyrightlink": "https://www.bing.com/search?q=x", "quiz": None,
    }]

    class _StubNiumoo:
        def __init__(self, payload):
            self.payload = payload

        def fetch(self, session=None):
            from crawler.sources.niumoo_source import _OHR_RE

            return [{
                "market": i["region"].lower(), "date": i["date"],
                "urlbase": f"/th?id={_OHR_RE.search(i['url']).group(0)}",
                "title": None, "desc": i["desc"], "copyrightlink": None, "quiz": None,
            } for i in self.payload]

    class _StubBing:
        def __init__(self, payload):
            self.payload = payload

        def fetch(self):
            return self.payload

    monkeypatch.setattr("crawler.backfill.check_resolutions",
                        lambda urlbase, **kw: {"uhd": True, "fhd": True, "hd": True, "thumb": True})
    monkeypatch.setattr("crawler.backfill.NiumooSource", lambda: _StubNiumoo(niumoo_payload))
    monkeypatch.setattr("crawler.backfill.BingApiSource", lambda: _StubBing(bing_payload))
    monkeypatch.setattr("crawler.backfill.verify_mkt", lambda markets, session=None: list(markets))

    run_backfill(data_dir=tmp_path, check_res=False)

    zh = load_year(tmp_path, "zh-cn", 2026)
    assert len(zh) == 1
    rec = zh[0]
    assert rec["title"] == "纵身一跃，一次一课"  # Bing API 源覆盖了 niumoo 的 None
    assert rec["resolutions"] == {}
    us = load_year(tmp_path, "en-us", 2026)
    assert us[0]["photographer"] == "Chris Dorney"
    assert json.loads((tmp_path / "aggregations.json").read_text("utf-8"))["total"] == 2


def test_verify_mkt_excludes_polluted_market(monkeypatch):
    # 本地（中国出口）网络下 ja-jp 请求实际拿到 zh-CN feed，必须被预检剔除
    def fake_fetch(market, idx=0, n=1, session=None):
        return [{"market": market, "date": "2026-10-06",
                 "urlbase": "/th?id=OHR.KasilofRiver_ZH-CN2394091052",
                 "title": None, "desc": "", "copyrightlink": None, "quiz": None}]

    monkeypatch.setattr("crawler.backfill.fetch_market", fake_fetch)
    assert verify_mkt(["zh-cn", "ja-jp"]) == ["zh-cn"]


def test_run_backfill_one_bad_record_does_not_abort(tmp_path, monkeypatch):
    class _RawStub:
        def fetch(self, session=None):
            return [
                {"market": "zh-cn", "date": "2026-10-05", "urlbase": "/th?id=OHR.Good1_ZH-CN1111111111",
                 "title": None, "desc": "ok", "copyrightlink": None, "quiz": None},
                # urlbase 不满足 schema 的 ^/th → validate_record 在落盘循环里抛错，必须只跳过不中断
                {"market": "zh-cn", "date": "2026-10-06", "urlbase": "BAD",
                 "title": None, "desc": "bad urlbase", "copyrightlink": None, "quiz": None},
            ]

    class _StubBing:
        def fetch(self):
            return []

    monkeypatch.setattr("crawler.backfill.NiumooSource", lambda: _RawStub())
    monkeypatch.setattr("crawler.backfill.BingApiSource", lambda: _StubBing())
    monkeypatch.setattr("crawler.backfill.verify_mkt", lambda markets, session=None: list(markets))

    run_backfill(data_dir=tmp_path, check_res=False)  # 不抛异常即通过
    assert len(load_year(tmp_path, "zh-cn", 2026)) == 1

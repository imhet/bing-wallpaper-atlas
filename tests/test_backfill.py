import json

import pytest

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
    assert rec["tags"] == ["南极", "antarctica", "antarctic", "南極"]  # build_record 必须接 geo_enrich


def test_build_record_copyright_field_fills_blank_parser():
    # npanuhin 深史源：desc 无 (© …) 括号，版权在独立 copyright 字段，用于补空解析
    merged = {
        "market": "en-us", "date": "2011-06-01",
        "urlbase": "https://bing.npanuhin.me/US/en/2011-06-01.jpg",
        "title": "Old title", "desc": "Just a description without copyright.",
        "copyright": "© dszc/Getty Images",
        "copyrightlink": None, "quiz": None,
    }
    rec = build_record(merged)
    assert rec["photographer"] == "dszc"
    assert rec["gallery"] == "Getty Images"


def test_build_record_desc_copyright_wins_over_field():
    merged = {
        "market": "en-us", "date": "2011-06-01",
        "urlbase": "https://bing.npanuhin.me/US/en/2011-06-01.jpg",
        "title": None, "desc": "Some place (© Otto Plantema/Minden Pictures)",
        "copyright": "© dszc/Getty Images",
        "copyrightlink": None, "quiz": None,
    }
    rec = build_record(merged)
    assert rec["photographer"] == "Otto Plantema"  # desc 括号解析优先，字段只补空


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
    monkeypatch.setattr("crawler.backfill.NpanuhinSource", lambda *a, **k: _StubBing([]))
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
    monkeypatch.setattr("crawler.backfill.NpanuhinSource", lambda *a, **k: _StubBing())
    monkeypatch.setattr("crawler.backfill.verify_mkt", lambda markets, session=None: list(markets))

    run_backfill(data_dir=tmp_path, check_res=False)  # 不抛异常即通过
    assert len(load_year(tmp_path, "zh-cn", 2026)) == 1


def test_mirror_records_not_blocked_by_preflight_failure_of_bing_sources(tmp_path, monkeypatch):
    # 预检按「源×记录」判定而非按市场聚合：niumoo/bing_api 的 en-us 被预检剔除时，
    # npanuhin 纯镜像记录（不同日期）不得连坐（首个真实回填暴露：4045 条被市场级标记全剔）
    class _StubNiumoo:
        def fetch(self, session=None):
            return [{"market": "en-us", "date": "2026-10-05", "urlbase": "/th?id=OHR.A_EN-US1111111111",
                     "title": None, "desc": "", "copyrightlink": None, "quiz": None}]

    class _StubNpanuhin:
        name = "npanuhin"
        needs_mkt_check = False

        def fetch(self, session=None):
            return [{"market": "en-us", "date": "2012-02-02",
                     "urlbase": "https://bing.npanuhin.me/US/en/2012-02-02.jpg",
                     "title": "t", "desc": "", "copyright": None,
                     "copyrightlink": None, "quiz": None}]

    class _StubEmpty:
        def fetch(self, session=None):
            return []

    monkeypatch.setattr("crawler.backfill.NiumooSource", lambda: _StubNiumoo())
    monkeypatch.setattr("crawler.backfill.BingApiSource", lambda: _StubEmpty())
    monkeypatch.setattr("crawler.backfill.NpanuhinSource", lambda *a, **k: _StubNpanuhin())
    monkeypatch.setattr("crawler.backfill.verify_mkt", lambda markets, session=None: [])  # 预检全失败
    monkeypatch.setattr("crawler.backfill.check_resolutions",
                        lambda urlbase, **kw: {"original": True} if urlbase.startswith("https://") else {})

    run_backfill(data_dir=tmp_path, check_res=False)
    assert load_year(tmp_path, "en-us", 2026) == []  # Bing 系源记录被剔
    assert len(load_year(tmp_path, "en-us", 2012)) == 1  # 镜像记录豁免入库


def test_npanuhin_source_skips_mkt_preflight(tmp_path, monkeypatch):
    # npanuhin 数据来自镜像归档而非 Bing 接口，无网络路由污染问题：
    # 不能因 en-us 预检失败把整个深史源卡掉（本地/受限网络下 en-us 预检会失败）
    preflight_calls = []

    class _StubNpanuhin:
        name = "npanuhin"
        needs_mkt_check = False

        def fetch(self, session=None):
            return [{"market": "en-us", "date": "2012-02-02",
                     "urlbase": "https://bing.npanuhin.me/US/en/2012-02-02.jpg",
                     "title": "t", "desc": "", "copyright": None,
                     "copyrightlink": None, "quiz": None}]

    class _StubEmpty:
        def fetch(self, session=None):
            return []

    monkeypatch.setattr("crawler.backfill.NiumooSource", lambda: _StubEmpty())
    monkeypatch.setattr("crawler.backfill.BingApiSource", lambda: _StubEmpty())
    monkeypatch.setattr("crawler.backfill.NpanuhinSource", lambda *a, **k: _StubNpanuhin())
    monkeypatch.setattr("crawler.backfill.verify_mkt",
                        lambda markets, session=None: preflight_calls.extend(markets) or [])
    monkeypatch.setattr("crawler.backfill.check_resolutions", lambda urlbase, **kw: {"original": True})

    run_backfill(data_dir=tmp_path, check_res=False)
    assert preflight_calls == []  # 只有镜像源时根本不调预检
    assert len(load_year(tmp_path, "en-us", 2012)) == 1  # 记录照常入库


def test_build_record_enriches_tags():
    merged = {
        "market": "zh-cn", "date": "2026-10-11",
        "urlbase": "/th?id=OHR.ZhangjiajieFog_ZH-CN1234567890",
        "title": None,
        "desc": "张家界国家森林公园的云海 (© Li Hua/Getty Images)",
        "copyrightlink": None, "quiz": None,
    }
    rec = build_record(merged)
    assert "张家界" in rec["tags"], "build_record 必须接 geo_enrich：tags 不能是空的"
    assert "湖南" in rec["tags"], "层级词典：命中张家界应连带父行政区湖南全组别名"

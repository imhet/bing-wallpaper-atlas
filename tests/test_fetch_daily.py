import crawler.fetch_daily as fd
from crawler.storage import load_year


def raw(market, date, key):
    return {"market": market, "date": date, "urlbase": f"/th?id=OHR.{key}_XX-XX1",
            "title": None, "desc": "somewhere, China (© A/B)", "copyrightlink": None, "quiz": None}


def test_daily_inserts_new_and_reports_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(fd, "fetch_market",
                        lambda market, idx=0, n=8: [raw(market, "2026-10-06", "NewOne")] if market == "zh-cn" else [])
    monkeypatch.setattr(fd, "check_resolutions", lambda urlbase, **kw: {"uhd": True, "fhd": True, "hd": True, "thumb": True})
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert changed is True and core_failed is False
    assert load_year(tmp_path, "zh-cn", 2026)[0]["id"] == "zh-cn-2026-10-06"


def test_daily_idempotent_no_change(tmp_path, monkeypatch):
    monkeypatch.setattr(fd, "fetch_market", lambda market, idx=0, n=8: [raw(market, "2026-10-06", "NewOne")])
    monkeypatch.setattr(fd, "check_resolutions", lambda urlbase, **kw: {"uhd": True, "fhd": True, "hd": True, "thumb": True})
    fd.run_daily(data_dir=tmp_path)
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert changed is False and core_failed is False


def test_core_failure_sets_flag_and_skips_extended(tmp_path, monkeypatch):
    calls = []

    def boom(market, idx=0, n=8):
        calls.append(market)
        if market == "zh-cn":
            raise fd.BingApiError("down")
        return []

    monkeypatch.setattr(fd, "fetch_market", boom)
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert core_failed is True
    assert "ja-jp" not in calls  # 核心失败后扩展市场确实未被请求


def test_bad_record_in_daily_does_not_poison_market(tmp_path, monkeypatch):
    def fetch(market, idx=0, n=8):
        if market != "zh-cn":
            return []
        return [
            {"market": "zh-cn", "date": "2026-10-06", "urlbase": "/th?id=OHR.Good_ZH-CN1111111111",
             "title": None, "desc": "ok", "copyrightlink": None, "quiz": None},
            {"market": "zh-cn", "date": "2026-10-07", "urlbase": "BAD",  # schema 校验会失败
             "title": None, "desc": "x", "copyrightlink": None, "quiz": None},
        ]

    monkeypatch.setattr(fd, "fetch_market", fetch)
    monkeypatch.setattr(fd, "check_resolutions", lambda urlbase, **kw: {"uhd": True, "fhd": True, "hd": True, "thumb": True})
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert core_failed is False
    assert len(load_year(tmp_path, "zh-cn", 2026)) == 1  # 坏记录跳过，好记录入库


def test_extended_failure_is_not_fatal(tmp_path, monkeypatch):
    def flaky(market, idx=0, n=8):
        if market == "ja-jp":
            raise fd.BingApiError("down")
        return [raw(market, "2026-10-06", "K")] if market == "zh-cn" else []

    monkeypatch.setattr(fd, "fetch_market", flaky)
    monkeypatch.setattr(fd, "check_resolutions", lambda urlbase, **kw: {"uhd": True})
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert core_failed is False and changed is True


def test_main_exits_1_on_core_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fd, "run_daily", lambda data_dir="data": (False, True))
    monkeypatch.setattr("sys.argv", ["fetch_daily.py", "--data-dir", str(tmp_path)])
    try:
        fd.main()
        code = 0
    except SystemExit as e:
        code = e.code
    assert code == 1

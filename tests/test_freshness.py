"""freshness_check 判定逻辑测试。"""
import datetime

from crawler.freshness_check import is_stale


def test_当天数据不红():
    assert is_stale("2026-11-15", datetime.date(2026, 11, 15)) is False


def test_落后一天在容忍范围内():
    assert is_stale("2026-11-14", datetime.date(2026, 11, 15)) is False


def test_落后两天红灯():
    assert is_stale("2026-11-13", datetime.date(2026, 11, 15)) is True


def test_落后三天红灯():
    assert is_stale("2026-11-12", datetime.date(2026, 11, 15)) is True


def test_自定义容忍天数():
    assert is_stale("2026-11-13", datetime.date(2026, 11, 15), max_lag_days=2) is False
    assert is_stale("2026-11-12", datetime.date(2026, 11, 15), max_lag_days=2) is True


def test_数据超前于今天不红():
    # 时区差导致的「未来日期」不算新鲜度问题（丢弃逻辑在入库侧）
    assert is_stale("2026-11-16", datetime.date(2026, 11, 15)) is False

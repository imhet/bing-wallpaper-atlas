import pytest

from crawler.merge import merge_records


def test_later_source_wins_on_conflict():
    a = {"market": "zh-cn", "date": "2023-10-05", "desc": "旧描述", "title": None}
    b = {"market": "zh-cn", "date": "2023-10-05", "desc": "新描述", "title": "标题"}
    merged = merge_records(a, b)
    assert merged["desc"] == "新描述"
    assert merged["title"] == "标题"


def test_later_source_fills_gaps_without_losing_data():
    a = {"market": "zh-cn", "date": "2023-10-05", "desc": "描述", "quiz": "q"}
    b = {"market": "zh-cn", "date": "2023-10-05", "desc": "描述", "title": "标题", "quiz": None}
    merged = merge_records(a, b)
    assert merged["title"] == "标题"
    assert merged["quiz"] == "q"


def test_key_conflict_raises():
    with pytest.raises(ValueError):
        merge_records({"market": "zh-cn", "date": "2023-10-05"}, {"market": "en-us", "date": "2023-10-05"})


def test_single_record_passthrough():
    r = {"market": "zh-cn", "date": "2023-10-05", "desc": "x"}
    assert merge_records(r) == r

import json

from crawler.storage import load_all, load_year, save_year, upsert_record, write_aggregations


def test_save_and_load_roundtrip(tmp_path, make_record):
    save_year(tmp_path, "zh-cn", 2023, [make_record(date="2023-10-05", id="zh-cn-2023-10-05"),
                                        make_record(date="2023-10-04", id="zh-cn-2023-10-04")])
    assert load_year(tmp_path, "zh-cn", 2023)[0]["date"] == "2023-10-04"  # 已按 date 升序
    assert load_year(tmp_path, "zh-cn", 2099) == []


def test_upsert_insert_and_idempotent(tmp_path, make_record):
    rec = make_record()
    assert upsert_record(tmp_path, rec) is True
    assert upsert_record(tmp_path, rec) is False  # 内容不变
    changed = make_record(title="新标题")
    assert upsert_record(tmp_path, changed) is True
    assert len(load_year(tmp_path, "zh-cn", 2023)) == 1


def test_load_all_scans_markets(tmp_path, make_record):
    upsert_record(tmp_path, make_record())
    upsert_record(tmp_path, make_record(market="en-us", id="en-us-2023-10-05"))
    all_data = load_all(tmp_path)
    assert set(all_data) == {"zh-cn", "en-us"}


def test_write_aggregations(tmp_path, make_record):
    upsert_record(tmp_path, make_record())
    upsert_record(tmp_path, make_record(market="en-us", id="en-us-2023-10-05", photographer="Li Hua"))
    upsert_record(tmp_path, make_record(market="en-us", id="en-us-2023-10-06", date="2023-10-06", photographer="Bob"))
    write_aggregations(tmp_path)
    agg = json.loads((tmp_path / "aggregations.json").read_text("utf-8"))
    # 下拉计数改由前端 computeFacets 动态计算（分面联动），聚合只留分片清单与站头字段
    assert agg["years_by_market"] == {"en-us": [2023], "zh-cn": [2023]}
    assert agg["latest_date"] == "2023-10-06"  # 数据自身属性，非抓取时间戳
    assert agg["total"] == 3
    assert "updated_at" not in agg  # 零 diff 约束：禁止时间戳字段
    # 退役字段不再生成（旧的全局计数不随筛选联动，已无消费方）
    assert not ({"markets", "years", "months", "regions", "photographers"} & set(agg))


def test_write_aggregations_empty(tmp_path):
    write_aggregations(tmp_path)
    agg = json.loads((tmp_path / "aggregations.json").read_text("utf-8"))
    assert agg["total"] == 0
    assert agg["latest_date"] is None


def test_load_all_ignores_aggregations_file(tmp_path, make_record):
    upsert_record(tmp_path, make_record())
    write_aggregations(tmp_path)
    assert set(load_all(tmp_path)) == {"zh-cn"}  # aggregations.json 不是市场目录

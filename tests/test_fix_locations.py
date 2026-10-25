"""fix_locations 的多线挖掘逻辑：主文本 → 同图组兄弟 → content_tags → region 兜底。"""

from crawler.fix_locations import recompute_record


def base_rec(**over):
    rec = {
        "id": "en-us-2013-07-01", "market": "en-us", "date": "2013-07-01",
        "urlbase": "https://bing.npanuhin.me/US/en/2013-07-01.jpg", "imageKey": "X",
        "title": None, "desc": "", "location": [], "region": None,
        "photographer": None, "gallery": None, "copyrightlink": None, "quiz": None,
        "resolutions": {}, "tags": [], "content_tags": [],
    }
    rec.update(over)
    return rec


def test_mines_locations_from_sibling_market():
    # 同图组兄弟市场（zh-cn 官方源）有准确地点：跨市场继承（挖成规范中文名）
    rec = base_rec(desc="A quiet lake at dusk")
    out = recompute_record(rec, siblings_loc_text="张家界国家森林公园, 湖南 (© Li)")
    assert "张家界" in out["location"] or "湖南" in out["location"]


def test_mines_locations_from_content_tags():
    # desc 全空的深史图：VLM 打标认出的地名概念也可挖
    rec = base_rec(content_tags=["京都", "寺庙", "红叶"])
    out = recompute_record(rec)
    assert "京都" in out["location"]


def test_region_falls_back_into_location_tail():
    # 主文本/兄弟/标签全无线索，但 region 已归一出国家（desc 里的国名不在地名词典时）：
    # 国家写入 location 兜底，详情页至少显示国别
    rec = base_rec(desc="Sunrise over remote islands far from the mainland", region="日本")
    out = recompute_record(rec)
    assert out["location"] == ["日本"]


def test_main_text_still_wins_over_siblings():
    # 自身文本能挖到时优先自身，兄弟只是兜底
    rec = base_rec(title="Winter in Yellowstone National Park")
    out = recompute_record(rec, siblings_loc_text="张家界国家森林公园, 湖南 (© Li)")
    assert out["location"] == ["黄石"]


def test_nothing_available_stays_empty():
    rec = base_rec(desc="A beautiful landscape with mountains and rivers")
    out = recompute_record(rec)
    assert out["location"] == []

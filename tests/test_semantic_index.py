import json

import pytest

from crawler.semantic_index import (
    build,
    build_concepts,
    concept_vocab,
    group_records,
    pack_shard,
    quantize,
    unpack_shard,
)


def make_ver(market, date, urlbase, image_key=None):
    rec = {"id": f"{market}-{date}", "market": market, "date": date, "urlbase": urlbase}
    if image_key:
        rec["imageKey"] = image_key
    return rec


def test_quantize_roundtrip_keeps_direction():
    vec = [0.0, 0.5, -0.25, 1.0, -0.75]
    qi, scale = quantize(vec)
    back = [v * scale for v in qi]
    # 量化误差不超过一个步长
    assert all(abs(a - b) <= scale for a, b in zip(vec, back))
    assert all(-127 <= v <= 127 for v in qi)


def test_quantize_all_zero_vector():
    qi, scale = quantize([0.0, 0.0, 0.0])
    assert qi == [0, 0, 0]
    assert scale == pytest.approx(0.0)


def test_pack_unpack_roundtrip():
    vec = [0.5, -0.5] * 256
    qi, scale = quantize(vec)
    data = pack_shard([("ChambordCastle", qi, scale), ("https://x/y.jpg", qi, scale)])
    rows = unpack_shard(data)
    assert [r[0] for r in rows] == ["ChambordCastle", "https://x/y.jpg"]
    assert rows[0][1] == qi
    assert rows[0][2] == pytest.approx(scale)


def test_pack_unpack_empty_shard():
    assert unpack_shard(pack_shard([])) == []


def test_group_records_prefers_zh_cn():
    recs = [
        make_ver("en-us", "2023-10-05", "/th?id=OHR.A_EN-US1"),
        make_ver("zh-cn", "2023-10-05", "/th?id=OHR.A_ZH-CN2"),
        make_ver("ja-jp", "2023-10-05", "/th?id=OHR.A_JA-JP3"),
    ]
    groups = group_records(recs)
    assert len(groups) == 1
    assert next(iter(groups.values()))["market"] == "zh-cn"


def _write_shards(data_dir, by_market):
    for market, recs in by_market.items():
        path = data_dir / market
        path.mkdir(parents=True, exist_ok=True)
        years = {}
        for rec in recs:
            years.setdefault(rec["date"][:4], []).append(rec)
        for year, rows in years.items():
            (path / f"{year}.json").write_text(json.dumps(rows), encoding="utf-8")


def _fake_vec(seed):
    return [float(seed)] * 512


def test_build_writes_one_shard_per_year(tmp_path):
    data_dir, out_dir = tmp_path / "data", tmp_path / "sem"
    _write_shards(
        data_dir,
        {
            "zh-cn": [make_ver("zh-cn", "2023-10-05", "/th?id=OHR.A_ZH-CN1"), make_ver("zh-cn", "2024-01-02", "/th?id=OHR.B_ZH-CN2")],
        },
    )
    calls = []
    stats = build(data_dir, out_dir, lambda rec: calls.append(rec["id"]) or _fake_vec(0.5))

    assert stats["added"] == 2
    assert sorted(p.name for p in out_dir.glob("*.bin")) == ["2023.bin", "2024.bin"]
    rows = unpack_shard((out_dir / "2023.bin").read_bytes())
    assert [r[0] for r in rows] == ["/th?id=OHR.A"]
    assert len(calls) == 2


def test_build_skips_already_indexed_groups(tmp_path):
    data_dir, out_dir = tmp_path / "data", tmp_path / "sem"
    _write_shards(data_dir, {"zh-cn": [make_ver("zh-cn", "2023-10-05", "/th?id=OHR.A_ZH-CN1")]})
    build(data_dir, out_dir, lambda rec: _fake_vec(0.5))

    calls = []
    stats = build(data_dir, out_dir, lambda rec: calls.append(rec["id"]) or _fake_vec(0.9))
    assert calls == []
    assert stats["added"] == 0
    assert stats["reused"] == 1


def test_build_keeps_old_years_when_adding(tmp_path):
    data_dir, out_dir = tmp_path / "data", tmp_path / "sem"
    _write_shards(data_dir, {"zh-cn": [make_ver("zh-cn", "2023-10-05", "/th?id=OHR.A_ZH-CN1")]})
    build(data_dir, out_dir, lambda rec: _fake_vec(0.5))
    _write_shards(
        data_dir,
        {"zh-cn": [make_ver("zh-cn", "2023-10-05", "/th?id=OHR.A_ZH-CN1"), make_ver("zh-cn", "2024-01-02", "/th?id=OHR.B_ZH-CN2")]},
    )
    build(data_dir, out_dir, lambda rec: _fake_vec(0.9))

    assert [r[0] for r in unpack_shard((out_dir / "2023.bin").read_bytes())] == ["/th?id=OHR.A"]
    assert [r[0] for r in unpack_shard((out_dir / "2024.bin").read_bytes())] == ["/th?id=OHR.B"]


def test_build_skips_group_when_encoding_fails(tmp_path):
    data_dir, out_dir = tmp_path / "data", tmp_path / "sem"
    _write_shards(
        data_dir,
        {"zh-cn": [make_ver("zh-cn", "2023-10-05", "/th?id=OHR.BAD_ZH-CN1"), make_ver("zh-cn", "2023-10-06", "/th?id=OHR.OK_ZH-CN2")]},
    )

    def encode(rec):
        if "BAD" in rec["urlbase"]:
            raise OSError("图片 404")
        return _fake_vec(0.5)

    stats = build(data_dir, out_dir, encode)
    assert stats["added"] == 1
    assert stats["failed"] == 1
    assert [r[0] for r in unpack_shard((out_dir / "2023.bin").read_bytes())] == ["/th?id=OHR.OK"]


def test_concept_vocab_keeps_frequent_tags_only():
    recs = [
        {"content_tags": ["晚霞", "森林"]},
        {"content_tags": ["晚霞", "森林"]},
        {"content_tags": ["晚霞"]},
        {"content_tags": []},
        {"content_tags": None},
    ]
    assert concept_vocab(recs, min_count=2) == ["晚霞", "森林"]
    assert concept_vocab(recs, min_count=4) == []


def test_build_concepts_writes_two_aligned_shards(tmp_path):
    data_dir, out_dir = tmp_path / "data", tmp_path / "sem"
    _write_shards(
        data_dir,
        {"zh-cn": [{"id": "a", "market": "zh-cn", "date": "2023-01-01", "urlbase": "/x", "content_tags": ["灯塔", "海"]}] * 5},
    )
    n = build_concepts(
        data_dir,
        out_dir,
        lambda w: [1.0 if w == "灯塔" else 0.0] * 512,
        lambda w: [0.0, 1.0] * 256,
    )
    assert n == 2
    clip = unpack_shard((out_dir / "concepts_clip.bin").read_bytes())
    bge = unpack_shard((out_dir / "concepts_bge.bin").read_bytes())
    assert [r[0] for r in clip] == [r[0] for r in bge] == ["灯塔", "海"]
    assert clip[0][1][0] == 127  # 灯塔的 CLIP 向量首维是最大值
    assert bge[0][1][1] == 127


def test_group_records_uses_image_key_when_present():
    # 镜像记录 urlbase 各市场不同路径，必须靠 imageKey 归组
    recs = [
        make_ver("en-us", "2015-01-01", "https://bing.npanuhin.me/US/en/2015-01-01.jpg", "Shared"),
        make_ver("de-de", "2015-01-01", "https://bing.npanuhin.me/DE/de/2015-01-01.jpg", "Shared"),
    ]
    groups = group_records(recs)
    assert list(groups) == ["Shared"]
    assert next(iter(groups.values()))["market"] == "en-us"

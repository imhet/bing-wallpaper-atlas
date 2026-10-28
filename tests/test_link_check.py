import json

from crawler.link_check import evaluate, probe_urls, sample_records


def _write_shard(tmp_path, market, year, dates):
    d = tmp_path / market
    d.mkdir(parents=True, exist_ok=True)
    recs = [
        {"id": f"{market}-{dt}", "market": market, "date": dt, "urlbase": f"/th?id=OHR.X_{market}_{i}"}
        for i, dt in enumerate(dates)
    ]
    (d / f"{year}.json").write_text(json.dumps(recs), encoding="utf-8")


def test_sample_covers_every_market_year_pair(tmp_path):
    _write_shard(tmp_path, "zh-cn", "2026", ["2026-01-01", "2026-01-02", "2026-01-03"])
    _write_shard(tmp_path, "en-us", "2010", ["2010-06-01", "2010-06-02"])
    picked = sample_records(tmp_path, sample=200)
    pairs = {(r["market"], r["date"][:4]) for r in picked}
    assert pairs == {("zh-cn", "2026"), ("en-us", "2010")}


def test_sample_caps_at_limit_but_keeps_layer_minimum(tmp_path):
    _write_shard(tmp_path, "zh-cn", "2026", [f"2026-01-{d:02d}" for d in range(1, 29)])
    _write_shard(tmp_path, "en-us", "2010", ["2010-06-01", "2010-06-02"])
    # 限额小于总记录数时，分层保底（每组 ≥2）仍必须满足
    picked = sample_records(tmp_path, sample=5)
    assert len(picked) == 5
    pairs = {(r["market"], r["date"][:4]) for r in picked}
    assert pairs == {("zh-cn", "2026"), ("en-us", "2010")}


def test_probe_url_bing_uses_fhd_mirror_uses_original():
    recs = [
        {"id": "a", "urlbase": "/th?id=OHR.X_EN-US1"},
        {"id": "b", "urlbase": "https://bing.npanuhin.me/US/en/2010-01-01.jpg"},
    ]

    class FakeSession:
        def __init__(self):
            self.urls = []

        def head(self, url, timeout=None, allow_redirects=True):
            self.urls.append(url)

            class R:
                status_code = 200

            return R()

    session = FakeSession()
    results = probe_urls(recs, session)
    assert session.urls == [
        "https://www.bing.com/th?id=OHR.X_EN-US1_1920x1080.jpg",
        "https://bing.npanuhin.me/US/en/2010-01-01.jpg",
    ]
    assert [r["ok"] for r in results] == [True, True]
    assert [r["id"] for r in results] == ["a", "b"]


def test_evaluate_thresholds():
    # 死链率超阈值 → 1；未知率过高 → 2（网络不可信）；健康 → 0
    assert evaluate(dead=1, probed=100, unknown=0) == (0, "1/100 (1.0%)")
    assert evaluate(dead=5, probed=100, unknown=0)[0] == 1
    assert evaluate(dead=0, probed=100, unknown=30) == (2, "30/130 unknown (23.1%)")
    assert evaluate(dead=0, probed=100, unknown=5) == (0, "0/100 (0.0%)")

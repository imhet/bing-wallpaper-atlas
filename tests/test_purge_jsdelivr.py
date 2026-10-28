from pathlib import Path

from crawler.purge_jsdelivr import PURGE_URL, collect_paths, purge


class FakeResponse:
    def __init__(self, ok):
        self.ok = ok


class FakeSession:
    """按调用次序返回预设结果；记录每次请求的 URL 供断言。"""

    def __init__(self, results):
        self.results = list(results)
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        return FakeResponse(self.results.pop(0) if self.results else False)


def test_collect_paths_covers_all_data_files(tmp_path):
    d = tmp_path / "data"
    (d / "zh-cn").mkdir(parents=True)
    (d / "sem").mkdir()
    (d / "zh-cn" / "2026.json").write_text("[]")
    (d / "zh-cn" / "2025.json").write_text("[]")
    (d / "sem" / "2026.bin").write_bytes(b"x")
    (d / "sem" / "concepts_clip.bin").write_bytes(b"x")
    (d / "thumbs" / "en-us").mkdir(parents=True)
    (d / "thumbs" / "en-us" / "2010.webp").write_bytes(b"x")  # 缩略图不在 purge 清单
    paths = collect_paths(d)
    assert paths == [
        "data/aggregations.json",
        "data/geo_aliases.json",
        "data/zh-cn/2025.json",
        "data/zh-cn/2026.json",
        "data/sem/2026.bin",
        "data/sem/concepts_clip.bin",
    ]


def test_purge_urls_point_at_repo_main():
    assert PURGE_URL.format(path="data/aggregations.json") == (
        "https://purge.jsdelivr.net/gh/imhet/bing-wallpaper-atlas@main/data/aggregations.json"
    )


def test_purge_counts_success_and_failure():
    session = FakeSession([True, False, False, False, True])
    # 第 2 个文件三次全失败（计 1 失败），第 3 个第三次成功
    ok, fail = purge(["data/a.json", "data/b.json", "data/c.json"], session)
    assert (ok, fail) == (2, 1)
    assert len(session.urls) == 5  # 成功提前 break（1+1），失败走满重试（3）


def test_purge_retries_network_failure_then_succeeds(monkeypatch):
    import crawler.purge_jsdelivr as mod

    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)  # 跳过重试间隔
    session = FakeSession([True])
    ok, fail = purge(["data/a.json"], session)
    assert (ok, fail) == (1, 0)

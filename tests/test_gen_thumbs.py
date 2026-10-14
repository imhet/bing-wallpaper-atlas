import io
import json

import pytest
from PIL import Image

from crawler.gen_thumbs import generate, thumb_path


def jpeg_bytes(w=960, h=540):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


class FakeFetcher:
    def __init__(self, fail_urls=()):
        self.calls = []
        self.fail_urls = set(fail_urls)

    def __call__(self, url):
        self.calls.append(url)
        if url in self.fail_urls:
            raise OSError("boom")
        return jpeg_bytes()


@pytest.fixture
def data_dir(tmp_path):
    # en-us 两条镜像记录（不同年）+ 一条 Bing 相对 urlbase；zh-cn 一条镜像记录
    en2010 = [
        {"id": "en-us-2010-01-01", "market": "en-us", "date": "2010-01-01", "urlbase": "https://bing.npanuhin.me/US/en/2010-01-01.jpg"},
        {"id": "en-us-2010-01-02", "market": "en-us", "date": "2010-01-02", "urlbase": "/th?id=OHR.Bing_ZH-CN1"},
    ]
    en2011 = [
        {"id": "en-us-2011-06-01", "market": "en-us", "date": "2011-06-01", "urlbase": "https://bing.npanuhin.me/US/en/2011-06-01.jpg"},
    ]
    zh2024 = [
        {"id": "zh-cn-2024-01-01", "market": "zh-cn", "date": "2024-01-01", "urlbase": "https://bing.npanuhin.me/CN/zh/2024-01-01.jpg"},
    ]
    for rel, recs in {"en-us/2010.json": en2010, "en-us/2011.json": en2011, "zh-cn/2024.json": zh2024}.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(recs, ensure_ascii=False))
    return tmp_path


def test_thumb_path_uses_market_year_date(data_dir):
    rec = {"market": "en-us", "date": "2010-01-01"}
    assert thumb_path(data_dir, rec) == data_dir / "thumbs" / "en-us" / "2010" / "2010-01-01.webp"


def test_generate_encodes_480w_webp(data_dir):
    stats = generate(data_dir, fetch=FakeFetcher())
    assert stats == {"done": 3, "skipped": 0, "failed": 0}
    p = data_dir / "thumbs" / "en-us" / "2010" / "2010-01-01.webp"
    assert p.exists()
    img = Image.open(p)
    assert img.format == "WEBP"
    assert img.width == 480
    assert img.height == 270  # 960x540 等比缩放


def test_generate_skips_bing_relative_records(data_dir):
    f = FakeFetcher()
    generate(data_dir, fetch=f)
    # 并发生成，顺序不定，断言集合
    assert sorted(f.calls) == [
        "https://bing.npanuhin.me/CN/zh/2024-01-01.jpg",
        "https://bing.npanuhin.me/US/en/2010-01-01.jpg",
        "https://bing.npanuhin.me/US/en/2011-06-01.jpg",
    ]


def test_generate_idempotent(data_dir):
    f = FakeFetcher()
    generate(data_dir, fetch=f)
    stats = generate(data_dir, fetch=f)
    assert len(f.calls) == 3  # 第二遍零下载
    assert stats == {"done": 0, "skipped": 3, "failed": 0}


def test_generate_continues_on_fetch_failure(data_dir):
    f = FakeFetcher(fail_urls={"https://bing.npanuhin.me/US/en/2010-01-01.jpg"})
    stats = generate(data_dir, fetch=f)
    assert stats == {"done": 2, "skipped": 0, "failed": 1}
    # 失败的没写文件，其余正常生成
    assert not (data_dir / "thumbs" / "en-us" / "2010" / "2010-01-01.webp").exists()
    assert (data_dir / "thumbs" / "en-us" / "2011" / "2011-06-01.webp").exists()


def test_generate_limit_stops_after_n_downloads(data_dir):
    f = FakeFetcher()
    stats = generate(data_dir, fetch=f, limit=1)
    assert stats == {"done": 1, "skipped": 0, "failed": 0}
    assert len(f.calls) == 1

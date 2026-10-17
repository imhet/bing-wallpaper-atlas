"""content_tags 的 VLM 通道：回复解析、降级逻辑与镜像原图缩放（API 调用本身不做单测）。"""

import io

import pytest
from PIL import Image

import crawler.content_tags as ct
from crawler.content_tags import _parse_vlm_tags


def test_parses_plain_json_array():
    assert _parse_vlm_tags('["雪山", "湖泊"]') == ["雪山", "湖泊"]


def test_parses_markdown_wrapped_json():
    assert _parse_vlm_tags('```json\n["熊猫", "竹林"]\n```') == ["熊猫", "竹林"]


def test_parses_json_with_leading_text():
    assert _parse_vlm_tags('好的，标签如下：\n["佛像", "悬崖"]') == ["佛像", "悬崖"]


def test_caps_at_max_tags():
    # 上限与 VLM_MAX_TAGS（20）一致：超出的标签截断（2026-10-16 泛词层级后主体+上位词更占名额）
    assert _parse_vlm_tags('["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u"]') == [
        "a", "b", "c", "d", "e", "f", "g", "h", "i", "j",
        "k", "l", "m", "n", "o", "p", "q", "r", "s", "t",
    ]


def test_drops_non_string_items():
    assert _parse_vlm_tags('["雪山", 123, null, "湖泊"]') == ["雪山", "湖泊"]


def test_returns_none_on_no_json():
    assert _parse_vlm_tags("这张图片很美") is None


def test_returns_none_on_non_list_json():
    assert _parse_vlm_tags('{"tags": ["雪山"]}') is None


def test_returns_none_on_empty():
    assert _parse_vlm_tags("") is None


def test_empty_array_is_valid_judgment_not_failure():
    # VLM 回复 [] 是「图中无可标注实体」的保守判断（晨雾/纯风景图），不是失败——
    # 不能降级 CLIP 硬凑词表标签（实证：2011 晨雾图被 CLIP 瞎标「狐狸+树懒」）
    assert _parse_vlm_tags("[]") == []


def test_all_invalid_items_yields_empty_list():
    assert _parse_vlm_tags("[123, null, \"\"]") == []


def test_vlm_model_env_override(monkeypatch):
    # 本地端点与 Actions 端点支持的模型名不同：允许 VLM_MODEL 覆盖，默认不变
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self):
            return '{"content": [{"type": "text", "text": "[\\"雪山\\"]"}]}'.encode()

    def fake_urlopen(req, timeout=None):
        captured["body"] = __import__("json").loads(req.data)
        return _Resp()

    monkeypatch.setenv("VLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://x")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setattr(ct.urllib.request, "urlopen", fake_urlopen)
    assert ct.vlm_tag_image(b"jpeg") == ["雪山"]
    assert captured["body"]["model"] == "deepseek-v4-pro"


def test_vlm_model_defaults_to_glm(monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self):
            return '{"content": [{"type": "text", "text": "[]"}]}'.encode()

    def fake_urlopen(req, timeout=None):
        captured["body"] = __import__("json").loads(req.data)
        return _Resp()

    monkeypatch.delenv("VLM_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://x")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setattr(ct.urllib.request, "urlopen", fake_urlopen)
    ct.vlm_tag_image(b"jpeg")
    assert captured["body"]["model"] == "glm-5.3-flash"


def _jpeg(width, height):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buf, "JPEG")
    return buf.getvalue()


def test_shrink_image_caps_width():
    w, h = Image.open(io.BytesIO(ct._shrink_image(_jpeg(1920, 1080)))).size
    assert (w, h) == (640, 360)


def test_shrink_image_small_image_passthrough():
    assert ct._shrink_image(_jpeg(400, 240)) == _jpeg(400, 240)


class _FakeResp:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


def test_fetch_thumb_absolute_url_gets_original_and_shrinks(monkeypatch):
    calls = []
    monkeypatch.setattr(ct.requests, "get", lambda url, timeout=None: calls.append(url) or _FakeResp(_jpeg(1920, 1080)))
    out = ct.fetch_thumb("https://bing.npanuhin.me/US/en/2011-06-01.jpg")
    assert calls == ["https://bing.npanuhin.me/US/en/2011-06-01.jpg"]  # 直拉镜像，不拼 Bing 前缀
    assert Image.open(io.BytesIO(out)).size == (640, 360)  # 本地缩图省 VLM token


def test_fetch_thumb_bing_relative_keeps_suffix(monkeypatch):
    calls = []
    monkeypatch.setattr(ct.requests, "get", lambda url, timeout=None: calls.append(url) or _FakeResp(b"jpeg"))
    out = ct.fetch_thumb("/th?id=OHR.X_ZH-CN1")
    assert calls == ["https://www.bing.com/th?id=OHR.X_ZH-CN1_400x240.jpg"]
    assert out == b"jpeg"

"""content_tags 的 VLM 通道：回复解析与降级逻辑（API 调用本身不做单测）。"""

import pytest

from crawler.content_tags import _parse_vlm_tags


def test_parses_plain_json_array():
    assert _parse_vlm_tags('["雪山", "湖泊"]') == ["雪山", "湖泊"]


def test_parses_markdown_wrapped_json():
    assert _parse_vlm_tags('```json\n["熊猫", "竹林"]\n```') == ["熊猫", "竹林"]


def test_parses_json_with_leading_text():
    assert _parse_vlm_tags('好的，标签如下：\n["佛像", "悬崖"]') == ["佛像", "悬崖"]


def test_caps_at_six_tags():
    assert _parse_vlm_tags('["a", "b", "c", "d", "e", "f", "g", "h"]') == ["a", "b", "c", "d", "e", "f"]


def test_drops_non_string_items():
    assert _parse_vlm_tags('["雪山", 123, null, "湖泊"]') == ["雪山", "湖泊"]


def test_returns_none_on_no_json():
    assert _parse_vlm_tags("这张图片很美") is None


def test_returns_none_on_non_list_json():
    assert _parse_vlm_tags('{"tags": ["雪山"]}') is None


def test_returns_none_on_empty():
    assert _parse_vlm_tags("") is None

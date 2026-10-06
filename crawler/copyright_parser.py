"""解析 Bing copyright 字符串：'内容 (© 摄影师/图库)'。

永不抛异常：解析不出就返回空值，调用方保留原始 desc。
"""

import re

_DATE_RE = re.compile(r"^(\d{4}年)?\d{1,2}月\d{1,2}日$")
# inner 用贪婪匹配吃到字符串最外层闭括号，兼容摄影师名内嵌套的括号（Bing desc 至多一个 © 括号块）
_BRACKET_RE = re.compile(r"[（(]\s*©\s*(?P<inner>.*)[)）]")


def _empty_result():
    return {"photographer": None, "gallery": None, "location": []}


def parse_copyright(desc):
    if not desc:
        return _empty_result()
    result = _empty_result()
    text = desc
    m = _BRACKET_RE.search(desc)
    if m:
        inner = m.group("inner").strip()
        inner = re.sub(r"[（(][^)）]*[)）]", "", inner).strip()  # 剥掉摄影师名内嵌套的配对括号
        if "/" in inner:
            photographer, _, gallery = inner.partition("/")
            result["photographer"] = photographer.strip() or None
            result["gallery"] = gallery.strip() or None
        else:
            result["photographer"] = inner or None
        text = (desc[: m.start()] + " " + desc[m.end() :]).strip()
    text = text.strip(" ,，、-–—")
    parts = [p.strip() for p in re.split(r"[,，]", text) if p.strip()]
    if parts and _DATE_RE.match(parts[-1]):
        parts = parts[:-1]
    result["location"] = parts
    return result

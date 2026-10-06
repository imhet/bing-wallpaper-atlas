"""从 urlbase 提取跨市场的图片标识。"""

import re

_RE = re.compile(r"OHR\.([A-Za-z0-9]+?)_[A-Z]{2}-[A-Z]{2}\d+$")


def extract_image_key(urlbase):
    if not urlbase:
        return None
    m = _RE.search(urlbase)
    return m.group(1) if m else None

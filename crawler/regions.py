"""国家/地区词表与提取。词表是可维护的起点清单，遇到未覆盖地区直接加条目。"""

import re

COUNTRY_ALIASES = {
    "中国": "中国", "中华人民共和国": "中国",
    "美国": "美国", "美利坚合众国": "美国", "united states": "美国", "usa": "美国", "us": "美国", "america": "美国",
    "英国": "英国", "英格兰": "英国", "苏格兰": "英国", "威尔士": "英国", "北爱尔兰": "英国",
    "united kingdom": "英国", "uk": "英国", "england": "英国", "scotland": "英国", "wales": "英国",
    "日本": "日本", "japan": "日本",
    "德国": "德国", "germany": "德国",
    "法国": "法国", "france": "法国",
    "韩国": "韩国", "south korea": "韩国", "korea": "韩国",
    "加拿大": "加拿大", "canada": "加拿大",
    "澳大利亚": "澳大利亚", "australia": "澳大利亚",
    "新西兰": "新西兰", "new zealand": "新西兰",
    "意大利": "意大利", "italy": "意大利",
    "西班牙": "西班牙", "spain": "西班牙",
    "葡萄牙": "葡萄牙", "portugal": "葡萄牙",
    "瑞士": "瑞士", "switzerland": "瑞士",
    "挪威": "挪威", "norway": "挪威",
    "瑞典": "瑞典", "sweden": "瑞典",
    "芬兰": "芬兰", "finland": "芬兰",
    "丹麦": "丹麦", "denmark": "丹麦", "法罗群岛": "丹麦", "faroe islands": "丹麦",
    "荷兰": "荷兰", "netherlands": "荷兰",
    "比利时": "比利时", "belgium": "比利时",
    "奥地利": "奥地利", "austria": "奥地利",
    "爱尔兰": "爱尔兰", "ireland": "爱尔兰",
    "希腊": "希腊", "greece": "希腊",
    "土耳其": "土耳其", "turkey": "土耳其",
    "俄罗斯": "俄罗斯", "russia": "俄罗斯",
    "印度": "印度", "india": "印度",
    "泰国": "泰国", "thailand": "泰国",
    "越南": "越南", "vietnam": "越南",
    "印度尼西亚": "印度尼西亚", "indonesia": "印度尼西亚",
    "马来西亚": "马来西亚", "malaysia": "马来西亚",
    "新加坡": "新加坡", "singapore": "新加坡",
    "菲律宾": "菲律宾", "philippines": "菲律宾",
    "尼泊尔": "尼泊尔", "nepal": "尼泊尔",
    "不丹": "不丹", "bhutan": "不丹",
    "缅甸": "缅甸", "myanmar": "缅甸", "burma": "缅甸",
    "柬埔寨": "柬埔寨", "cambodia": "柬埔寨",
    "老挝": "老挝", "laos": "老挝",
    "斯里兰卡": "斯里兰卡", "sri lanka": "斯里兰卡",
    "巴基斯坦": "巴基斯坦", "pakistan": "巴基斯坦",
    "哈萨克斯坦": "哈萨克斯坦", "kazakhstan": "哈萨克斯坦",
    "蒙古": "蒙古", "mongolia": "蒙古",
    "巴西": "巴西", "brazil": "巴西",
    "墨西哥": "墨西哥", "mexico": "墨西哥",
    "阿根廷": "阿根廷", "argentina": "阿根廷",
    "智利": "智利", "chile": "智利",
    "秘鲁": "秘鲁", "peru": "秘鲁",
    "哥伦比亚": "哥伦比亚", "colombia": "哥伦比亚",
    "厄瓜多尔": "厄瓜多尔", "ecuador": "厄瓜多尔",
    "玻利维亚": "玻利维亚", "bolivia": "玻利维亚",
    "乌拉圭": "乌拉圭", "uruguay": "乌拉圭",
    "委内瑞拉": "委内瑞拉", "venezuela": "委内瑞拉",
    "哥斯达黎加": "哥斯达黎加", "costa rica": "哥斯达黎加",
    "巴拿马": "巴拿马", "panama": "巴拿马",
    "南非": "南非", "south africa": "南非",
    "埃及": "埃及", "egypt": "埃及",
    "摩洛哥": "摩洛哥", "morocco": "摩洛哥",
    "突尼斯": "突尼斯", "tunisia": "突尼斯",
    "肯尼亚": "肯尼亚", "kenya": "肯尼亚",
    "坦桑尼亚": "坦桑尼亚", "tanzania": "坦桑尼亚",
    "纳米比亚": "纳米比亚", "namibia": "纳米比亚",
    "博茨瓦纳": "博茨瓦纳", "botswana": "博茨瓦纳",
    "马达加斯加": "马达加斯加", "madagascar": "马达加斯加",
    "南极洲": "南极洲", "antarctica": "南极洲",
    "阿联酋": "阿联酋", "united arab emirates": "阿联酋",
    "沙特阿拉伯": "沙特阿拉伯", "saudi arabia": "沙特阿拉伯",
    "约旦": "约旦", "jordan": "约旦",
    "以色列": "以色列", "israel": "以色列",
    "克罗地亚": "克罗地亚", "croatia": "克罗地亚",
    "匈牙利": "匈牙利", "hungary": "匈牙利",
    "捷克": "捷克", "czech republic": "捷克", "czechia": "捷克",
    "波兰": "波兰", "poland": "波兰",
    "保加利亚": "保加利亚", "bulgaria": "保加利亚",
    "斯洛文尼亚": "斯洛文尼亚", "slovenia": "斯洛文尼亚",
    "斯洛伐克": "斯洛伐克", "slovakia": "斯洛伐克",
    "罗马尼亚": "罗马尼亚", "romania": "罗马尼亚",
    "冰岛": "冰岛", "iceland": "冰岛",
    "格陵兰": "格陵兰", "greenland": "格陵兰",
}

_LOWERED = {k.lower(): v for k, v in COUNTRY_ALIASES.items()}

# 含这些短语时，对应别名的全文匹配作废（大洲/地区名不是国家）
_NEGATIVE_PHRASES = {
    "america": ["south america", "north america", "latin america"],
    "korea": ["north korea"],
}


def _contains(alias, text):
    # 拉丁别名一律按词边界匹配：'us' 不能命中 'russia'，'america' 不能命中 'American'
    if alias.isascii():
        if not re.search(rf"\b{re.escape(alias)}\b", text):
            return False
        for phrase in _NEGATIVE_PHRASES.get(alias, []):
            if phrase in text:
                return False
        return True
    return alias in text


def extract_region(location, full_text):
    for part in reversed(location or []):
        hit = _LOWERED.get(part.strip().lower())
        if hit:
            return hit
    text = (full_text or "").lower()
    hits = [(len(alias), canonical) for alias, canonical in _LOWERED.items() if _contains(alias, text)]
    if hits:
        return max(hits)[1]
    return None

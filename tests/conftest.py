import pytest


@pytest.fixture
def make_record():
    def _make(**over):
        rec = {
            "id": "zh-cn-2023-10-05",
            "market": "zh-cn",
            "date": "2023-10-05",
            "urlbase": "/th?id=OHR.ZhangjiajieMist_ZH-CN1234567890",
            "imageKey": "ZhangjiajieMist",
            "title": "云海仙境",
            "desc": "张家界云海 (© Li Hua/Getty Images)",
            "location": ["张家界云海"],
            "region": "中国",
            "photographer": "Li Hua",
            "gallery": "Getty Images",
            "copyrightlink": None,
            "quiz": None,
            "resolutions": {"uhd": True, "fhd": True, "hd": True, "thumb": True},
            "tags": [],
        }
        rec.update(over)
        return rec
    return _make

from crawler.resolutions import RESOLUTION_SUFFIXES, check_resolutions


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeSession:
    def __init__(self, status_map):
        self.status_map = status_map
        self.urls = []

    def head(self, url, timeout=None, allow_redirects=True):
        self.urls.append(url)
        for suffix, status in self.status_map.items():
            if url.endswith(suffix):
                return FakeResponse(status)
        return FakeResponse(404)


def test_suffix_list():
    keys = [k for k, _ in RESOLUTION_SUFFIXES]
    assert keys == ["uhd", "fhd", "hd", "thumb"]
    assert dict(RESOLUTION_SUFFIXES)["uhd"] == "_UHD.jpg"


def test_check():
    session = FakeSession({"_UHD.jpg": 200, "_1920x1080.jpg": 200, "_1366x768.jpg": 404, "_400x240.jpg": 200})
    result = check_resolutions("/th?id=OHR.Test_ZH-CN1234567890", session=session)
    assert result == {"uhd": True, "fhd": True, "hd": False, "thumb": True}
    assert len(session.urls) == 4
    assert session.urls[0] == "https://www.bing.com/th?id=OHR.Test_ZH-CN1234567890_UHD.jpg"


def test_all_network_errors_return_empty():
    # 系统性网络故障返回 {}：与"图链 404 是真实状态"区分，让回填下轮重试
    class Dead:
        def head(self, url, timeout=None, allow_redirects=True):
            raise ConnectionError("down")

    assert check_resolutions("/th?id=OHR.X_ZH-CN1", session=Dead()) == {}


def test_partial_network_failure_does_not_freeze_false():
    # 部分档网络抖动也不得固化 false——整条返回 {} 待下轮重试（修复 HEAD 抖动 diff 噪音）
    class FlakyOnce:
        def head(self, url, timeout=None, allow_redirects=True):
            if url.endswith("_400x240.jpg"):
                raise ConnectionError("blip")
            return FakeResponse(200)

    assert check_resolutions("/th?id=OHR.X_ZH-CN1", session=FlakyOnce()) == {}

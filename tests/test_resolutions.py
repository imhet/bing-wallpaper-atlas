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


def test_check(monkeypatch):
    monkeypatch.setattr("crawler.resolutions.time.sleep", lambda s: None)
    session = FakeSession({"_UHD.jpg": 200, "_1920x1080.jpg": 200, "_1366x768.jpg": 404, "_400x240.jpg": 200})
    result = check_resolutions("/th?id=OHR.Test_ZH-CN1234567890", session=session)
    assert result == {"uhd": True, "fhd": True, "hd": False, "thumb": True}
    assert len(session.urls) == 4
    assert session.urls[0] == "https://www.bing.com/th?id=OHR.Test_ZH-CN1234567890_UHD.jpg"


def test_single_network_error_means_false(monkeypatch):
    monkeypatch.setattr("crawler.resolutions.time.sleep", lambda s: None)

    class Flaky:
        def __init__(self):
            self.n = 0

        def head(self, url, timeout=None, allow_redirects=True):
            self.n += 1
            if self.n == 1:
                raise ConnectionError("down")  # 单次网络错误
            return FakeResponse(200)

    result = check_resolutions("/th?id=OHR.X_ZH-CN1", session=Flaky())
    assert result["uhd"] is False  # 单档失败记 false
    assert result["fhd"] is True


def test_all_network_errors_return_empty(monkeypatch):
    # 系统性网络故障返回 {}：与"图链 404 是真实状态"区分，让回填下轮重试
    monkeypatch.setattr("crawler.resolutions.time.sleep", lambda s: None)

    class Dead:
        def head(self, url, timeout=None, allow_redirects=True):
            raise ConnectionError("down")

    assert check_resolutions("/th?id=OHR.X_ZH-CN1", session=Dead()) == {}

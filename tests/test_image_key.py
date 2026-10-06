from crawler.image_key import extract_image_key


def test_extract():
    assert extract_image_key("/th?id=OHR.DanxiaLandform_ZH-CN2386060246") == "DanxiaLandform"


def test_none_when_no_match():
    assert extract_image_key("/th?id=whatever") is None
    assert extract_image_key("") is None

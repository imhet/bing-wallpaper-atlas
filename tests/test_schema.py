import pytest

from crawler.schema import validate_record


def test_valid_record_passes(make_record):
    validate_record(make_record())


def test_missing_field_fails(make_record):
    rec = make_record()
    del rec["urlbase"]
    with pytest.raises(Exception):
        validate_record(rec)


def test_extra_field_fails(make_record):
    with pytest.raises(Exception):
        validate_record(make_record(surprise="x"))


def test_bad_date_format_fails(make_record):
    with pytest.raises(Exception):
        validate_record(make_record(date="2023/10/05"))


def test_nullables_accepted(make_record):
    rec = make_record(title=None, imageKey=None, region=None, photographer=None, gallery=None)
    validate_record(rec)


def test_absolute_mirror_url_accepted(make_record):
    # npanuhin 深史源：老图无 OHR ID，urlbase 存镜像绝对 URL
    validate_record(make_record(urlbase="https://bing.npanuhin.me/US/en/2011-06-01.jpg"))


def test_non_th_relative_url_rejected(make_record):
    with pytest.raises(Exception):
        validate_record(make_record(urlbase="/images/foo.jpg"))


def test_resolutions_must_be_bool(make_record):
    with pytest.raises(Exception):
        validate_record(make_record(resolutions={"uhd": "yes"}))


def test_content_tags_optional_and_valid(make_record):
    # CLIP 打标产物：打标前不存在（可选），存在时必须是字符串数组
    validate_record(make_record())
    validate_record(make_record(content_tags=["雪山", "湖泊"]))

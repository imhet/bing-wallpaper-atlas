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


def test_resolutions_must_be_bool(make_record):
    with pytest.raises(Exception):
        validate_record(make_record(resolutions={"uhd": "yes"}))

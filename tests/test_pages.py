import pytest

from textbook_tw.pages import format_pages, parse_pages


def test_empty_spec_means_all_pages():
    assert parse_pages(None, 3) == [0, 1, 2]
    assert parse_pages("", 3) == [0, 1, 2]


def test_ranges_and_single_pages():
    assert parse_pages("1-3, 5", 6) == [0, 1, 2, 4]
    assert parse_pages("4-", 6) == [3, 4, 5]
    assert parse_pages("-2", 6) == [0, 1]
    assert parse_pages("3,1-2,2", 6) == [0, 1, 2]


@pytest.mark.parametrize("spec", ["0", "7", "5-3", "1-7"])
def test_out_of_range_is_rejected(spec):
    with pytest.raises(ValueError):
        parse_pages(spec, 6)


def test_format_is_inverse_of_parse():
    assert format_pages([0, 1, 2, 7]) == "1-3,8"
    assert format_pages([4]) == "5"
    for spec in ["1-3,8", "2,4,6-9", "1"]:
        assert format_pages(parse_pages(spec, 10)) == spec

from datetime import date

from book_sales_tracker.google_books import (
    _parse_published_date,
    _publication_overlaps_range,
)


def test_parse_published_date_year():
    start, end = _parse_published_date("2024")
    assert start == date(2024, 1, 1)
    assert end == date(2024, 12, 31)


def test_parse_published_date_month():
    start, end = _parse_published_date("2024-06")
    assert start == date(2024, 6, 1)
    assert end == date(2024, 6, 30)


def test_publication_overlap():
    assert _publication_overlaps_range("2024", date(2024, 1, 1), date(2024, 12, 31))
    assert not _publication_overlaps_range("2023", date(2024, 1, 1), date(2024, 12, 31))

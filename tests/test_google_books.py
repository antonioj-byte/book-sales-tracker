from datetime import date

from book_sales_tracker.google_books import (
    _normalize_publisher_name,
    _publisher_match_score,
    _publisher_names_match,
    _parse_published_date,
    _publication_overlaps_range,
    _publisher_search_queries_for_range,
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


def test_publisher_match_score():
    assert _publisher_match_score("Libros del Asteroide", "Libros del Asteroide") == 1.0
    assert _publisher_match_score("Anagrama", "Editorial Anagrama") >= 0.9
    assert _publisher_names_match("Libros del Asteroide", "LIBROS DEL ASTeroide, S.L.")


def test_publisher_search_queries_for_range_includes_years():
    queries = _publisher_search_queries_for_range(
        "Nordica Libros",
        date(2024, 1, 1),
        date(2026, 8, 21),
    )
    query_strings = [item[0] for item in queries]
    assert "inpublisher:Nordica Libros 2024" in query_strings
    assert 'inpublisher:"Nordica Libros" 2026' in query_strings
    assert any(year_scoped for _, year_scoped in queries)

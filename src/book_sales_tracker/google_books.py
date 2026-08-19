import re
import time

import httpx

from book_sales_tracker.marketplace import MarketplaceConfig
from book_sales_tracker.models import BookMetadata, BookSearchResult

GOOGLE_BOOKS_BASE = "https://www.googleapis.com/books/v1/volumes"
MAX_RETRIES = 3


class GoogleBooksError(Exception):
    pass


class BookNotFoundError(GoogleBooksError):
    pass


def normalize_isbn(raw: str) -> str:
    cleaned = re.sub(r"[^0-9Xx]", "", raw.strip())
    if not cleaned:
        raise ValueError("ISBN vacío o inválido")
    return cleaned.upper()


def _parse_volume(item: dict) -> BookMetadata:
    info = item.get("volumeInfo", {})
    isbn_10 = None
    isbn_13 = None
    for identifier in info.get("industryIdentifiers", []):
        id_type = identifier.get("type", "")
        value = identifier.get("identifier")
        if id_type == "ISBN_10":
            isbn_10 = value
        elif id_type == "ISBN_13":
            isbn_13 = value

    thumbnails = info.get("imageLinks", {})
    thumbnail = thumbnails.get("thumbnail") or thumbnails.get("smallThumbnail")

    return BookMetadata(
        title=info.get("title", "Sin título"),
        authors=info.get("authors", []),
        publisher=info.get("publisher"),
        published_date=info.get("publishedDate"),
        categories=info.get("categories", []),
        isbn_10=isbn_10,
        isbn_13=isbn_13,
        google_books_id=item.get("id"),
        thumbnail_url=thumbnail,
    )


def _format_search_label(metadata: BookMetadata) -> str:
    authors = ", ".join(metadata.authors) if metadata.authors else "Autor desconocido"
    isbn = metadata.isbn_13 or metadata.isbn_10 or "ISBN no disponible"
    publisher = metadata.publisher or "Editorial desconocida"
    return f"{metadata.title} — {authors} ({publisher}, {isbn})"


def _request_volumes(params: dict, api_key: str | None) -> dict:
    query_params = dict(params)
    if api_key:
        query_params["key"] = api_key

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        with httpx.Client(timeout=30.0) as client:
            response = client.get(GOOGLE_BOOKS_BASE, params=query_params)

        if response.status_code == 429 and attempt < MAX_RETRIES - 1:
            time.sleep(2 ** attempt)
            continue

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        return response.json()

    raise GoogleBooksError(f"Google Books no respondió: {last_error}")


def fetch_by_isbn(
    isbn: str,
    marketplace: MarketplaceConfig,
    api_key: str | None = None,
) -> BookMetadata:
    normalized = normalize_isbn(isbn)
    payload = _request_volumes(
        {
            "q": f"isbn:{normalized}",
            "country": marketplace.google_books_country,
            "maxResults": 5,
        },
        api_key,
    )
    if payload.get("totalItems", 0) == 0 or not payload.get("items"):
        raise BookNotFoundError(f"No se encontró ningún libro con ISBN {normalized}")

    return _parse_volume(payload["items"][0])


def search_by_title(
    title: str,
    marketplace: MarketplaceConfig,
    api_key: str | None = None,
    max_results: int = 10,
) -> list[BookSearchResult]:
    title = title.strip()
    if not title:
        raise ValueError("El título no puede estar vacío")

    payload = _request_volumes(
        {
            "q": f'intitle:"{title}"',
            "country": marketplace.google_books_country,
            "langRestrict": marketplace.google_books_lang,
            "maxResults": max_results,
            "orderBy": "relevance",
        },
        api_key,
    )
    if payload.get("totalItems", 0) == 0 or not payload.get("items"):
        raise BookNotFoundError(f"No se encontró ningún libro con título «{title}»")

    results: list[BookSearchResult] = []
    for item in payload["items"]:
        metadata = _parse_volume(item)
        results.append(
            BookSearchResult(
                metadata=metadata,
                display_label=_format_search_label(metadata),
            )
        )
    return results

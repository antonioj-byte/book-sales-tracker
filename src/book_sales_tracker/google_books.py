import calendar
import re
import time
from datetime import date, datetime

import httpx

from book_sales_tracker.marketplace import MarketplaceConfig
from book_sales_tracker.models import (
    BookMetadata,
    BookSearchResult,
    PublisherCatalogResult,
    PublisherSuggestion,
)

GOOGLE_BOOKS_BASE = "https://www.googleapis.com/books/v1/volumes"
MAX_RETRIES = 4


class GoogleBooksError(Exception):
    pass


class GoogleBooksUnavailableError(GoogleBooksError):
    """Google Books respondió con un error transitorio (503, 429, etc.)."""


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

        if response.status_code in {500, 502, 503, 504} and attempt < MAX_RETRIES - 1:
            time.sleep(2 ** attempt)
            continue

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            status = exc.response.status_code
            if status in {429, 500, 502, 503, 504}:
                raise GoogleBooksUnavailableError(
                    "Google Books no está disponible temporalmente "
                    f"(HTTP {status}). Espera unos segundos e inténtalo de nuevo."
                ) from exc
            raise GoogleBooksError(
                f"Google Books devolvió un error (HTTP {status}). "
                "Revisa la clave `GOOGLE_BOOKS_API_KEY` o prueba otra búsqueda."
            ) from exc
        return response.json()

    raise GoogleBooksUnavailableError(
        "Google Books no respondió tras varios intentos. Inténtalo de nuevo en unos segundos."
    ) from last_error


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


def _parse_published_date(value: str | None) -> tuple[date | None, date | None]:
    """Devuelve (inicio, fin) del periodo de publicación inferido del campo de Google Books."""
    if not value:
        return None, None
    cleaned = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            if fmt == "%Y-%m-%d":
                parsed = datetime.strptime(cleaned, fmt).date()
                return parsed, parsed
            if fmt == "%Y-%m":
                parsed = datetime.strptime(cleaned, fmt).date()
                last_day = calendar.monthrange(parsed.year, parsed.month)[1]
                return parsed.replace(day=1), parsed.replace(day=last_day)
            if fmt == "%Y":
                year = int(cleaned[:4])
                return date(year, 1, 1), date(year, 12, 31)
        except ValueError:
            continue
    return None, None


def _publication_overlaps_range(
    published_date: str | None,
    range_start: date,
    range_end: date,
) -> bool:
    pub_start, pub_end = _parse_published_date(published_date)
    if pub_start is None or pub_end is None:
        return False
    return pub_start <= range_end and pub_end >= range_start


def _normalize_publisher_name(value: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", value.lower())
    return " ".join(cleaned.split())


def _publisher_match_score(query: str, publisher: str | None) -> float:
    if not publisher:
        return 0.0
    query_norm = _normalize_publisher_name(query)
    publisher_norm = _normalize_publisher_name(publisher)
    if not query_norm or not publisher_norm:
        return 0.0
    if query_norm == publisher_norm:
        return 1.0
    if query_norm in publisher_norm or publisher_norm in query_norm:
        return 0.9
    query_tokens = set(query_norm.split())
    publisher_tokens = set(publisher_norm.split())
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens & publisher_tokens) / len(query_tokens)
    return overlap


def _publisher_names_match(confirmed: str, candidate: str | None) -> bool:
    if not candidate:
        return False
    confirmed_norm = _normalize_publisher_name(confirmed)
    candidate_norm = _normalize_publisher_name(candidate)
    if confirmed_norm == candidate_norm:
        return True
    return confirmed_norm in candidate_norm or candidate_norm in confirmed_norm


def _publisher_search_queries(query: str) -> list[str]:
    query = query.strip()
    return [
        f"inpublisher:{query}",
        f'inpublisher:"{query}"',
        query,
    ]


def _fetch_volume_pages(
    query: str,
    marketplace: MarketplaceConfig,
    api_key: str | None,
    *,
    max_volumes: int = 120,
) -> list[dict]:
    items: list[dict] = []
    start_index = 0
    page_size = 40

    while len(items) < max_volumes:
        payload = _request_volumes(
            {
                "q": query,
                "country": marketplace.google_books_country,
                "langRestrict": marketplace.google_books_lang,
                "maxResults": min(page_size, max_volumes - len(items)),
                "startIndex": start_index,
                "orderBy": "newest",
            },
            api_key,
        )
        batch = payload.get("items") or []
        if not batch:
            break
        items.extend(batch)
        start_index += len(batch)
        total = int(payload.get("totalItems") or 0)
        if start_index >= total or len(batch) < page_size:
            break
    return items


def discover_publishers(
    query: str,
    marketplace: MarketplaceConfig,
    api_key: str | None = None,
    max_volumes: int = 120,
) -> list[PublisherSuggestion]:
    query = query.strip()
    if not query:
        raise ValueError("El nombre de la editorial no puede estar vacío")

    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    scores: dict[str, float] = {}
    seen_items: set[str] = set()

    transient_errors = 0
    for search_query in _publisher_search_queries(query):
        try:
            page_items = _fetch_volume_pages(
                search_query, marketplace, api_key, max_volumes=max_volumes
            )
        except GoogleBooksUnavailableError:
            transient_errors += 1
            continue

        for item in page_items:
            item_id = item.get("id") or str(item)
            if item_id in seen_items:
                continue
            seen_items.add(item_id)

            metadata = _parse_volume(item)
            if not metadata.publisher:
                continue
            score = _publisher_match_score(query, metadata.publisher)
            if score < 0.4:
                continue

            name = metadata.publisher.strip()
            counts[name] = counts.get(name, 0) + 1
            scores[name] = max(scores.get(name, 0.0), score)
            samples.setdefault(name, [])
            if len(samples[name]) < 3:
                samples[name].append(metadata.title)

    suggestions = [
        PublisherSuggestion(
            name=name,
            volume_count=count,
            sample_titles=samples.get(name, []),
            match_score=round(scores.get(name, 0.0), 2),
        )
        for name, count in counts.items()
    ]
    suggestions.sort(key=lambda item: (item.match_score, item.volume_count), reverse=True)
    if suggestions:
        return suggestions[:12]
    if transient_errors == len(_publisher_search_queries(query)):
        raise GoogleBooksUnavailableError(
            "Google Books no está disponible temporalmente. "
            "Espera unos segundos e inténtalo de nuevo, o usa **Usar mi texto tal cual**."
        )
    return []


def search_publisher_catalog(
    publisher_confirmed: str,
    marketplace: MarketplaceConfig,
    pub_start: date,
    pub_end: date,
    api_key: str | None = None,
    max_results: int = 120,
) -> PublisherCatalogResult:
    publisher_confirmed = publisher_confirmed.strip()
    if not publisher_confirmed:
        raise ValueError("Debes confirmar el nombre de la editorial.")
    if pub_start > pub_end:
        raise ValueError("La fecha de inicio debe ser anterior o igual a la de fin.")

    collected: dict[str, BookMetadata] = {}
    seen_items: set[str] = set()
    volumes_scanned = 0
    matched_publisher = 0
    in_date_range = 0
    with_isbn = 0
    queries_tried: list[str] = []

    transient_errors = 0
    for search_query in _publisher_search_queries(publisher_confirmed):
        queries_tried.append(search_query)
        try:
            items = _fetch_volume_pages(
                search_query, marketplace, api_key, max_volumes=max_results * 3
            )
        except GoogleBooksUnavailableError:
            transient_errors += 1
            continue
        if not items:
            continue

        for item in items:
            item_id = item.get("id") or str(item)
            if item_id in seen_items:
                continue
            seen_items.add(item_id)
            volumes_scanned += 1

            metadata = _parse_volume(item)
            if not _publisher_names_match(publisher_confirmed, metadata.publisher):
                continue
            matched_publisher += 1

            if not _publication_overlaps_range(metadata.published_date, pub_start, pub_end):
                continue
            in_date_range += 1

            isbn_key = metadata.isbn_13 or metadata.isbn_10
            if not isbn_key:
                continue
            with_isbn += 1

            if isbn_key not in collected:
                collected[isbn_key] = metadata
            if len(collected) >= max_results:
                break

        if len(collected) >= max_results:
            break

    if not collected and transient_errors == len(_publisher_search_queries(publisher_confirmed)):
        raise GoogleBooksUnavailableError(
            "Google Books no está disponible temporalmente. "
            "Espera unos segundos e inténtalo de nuevo."
        )

    books = list(collected.values())
    books.sort(key=lambda book: book.published_date or "", reverse=True)
    return PublisherCatalogResult(
        publisher_confirmed=publisher_confirmed,
        books=books,
        volumes_scanned=volumes_scanned,
        matched_publisher=matched_publisher,
        in_date_range=in_date_range,
        with_isbn=with_isbn,
        queries_tried=queries_tried,
    )


def search_by_publisher(
    publisher: str,
    marketplace: MarketplaceConfig,
    pub_start: date,
    pub_end: date,
    api_key: str | None = None,
    max_results: int = 120,
) -> list[BookMetadata]:
    result = search_publisher_catalog(
        publisher, marketplace, pub_start, pub_end, api_key, max_results
    )
    return result.books


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

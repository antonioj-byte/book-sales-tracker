from datetime import date

from book_sales_tracker.bsr_processor import filter_and_resample_daily, summarize_bsr_series
from book_sales_tracker.config import Settings
from book_sales_tracker.google_books import (
    BookNotFoundError,
    fetch_by_isbn,
    normalize_isbn,
    search_by_title,
)
from book_sales_tracker.keepa_client import (
    KeepaError,
    KeepaNoSalesRankError,
    KeepaProductNotFoundError,
    fetch_product_by_isbn,
)
from book_sales_tracker.llm_estimator import LlmEstimatorError, estimate_sales
from book_sales_tracker.marketplace import MarketplaceConfig, get_marketplace
from book_sales_tracker.models import BookMetadata, PipelineResult


class PipelineError(Exception):
    pass


def run_pipeline(
    settings: Settings,
    *,
    isbn: str | None,
    book: BookMetadata | None,
    marketplace_code: str,
    start_date: date,
    end_date: date,
) -> PipelineResult:
    if start_date > end_date:
        raise PipelineError("La fecha de inicio debe ser anterior o igual a la fecha de fin.")

    marketplace = get_marketplace(marketplace_code)

    if book is None:
        if not isbn:
            raise PipelineError("Se requiere ISBN o metadatos de libro.")
        try:
            book = fetch_by_isbn(
                isbn,
                marketplace,
                api_key=settings.google_books_api_key,
            )
        except BookNotFoundError as exc:
            raise PipelineError(str(exc)) from exc

    resolved_isbn = book.isbn_13 or book.isbn_10 or (normalize_isbn(isbn) if isbn else None)
    if not resolved_isbn:
        raise PipelineError("No se pudo determinar un ISBN válido para consultar Keepa.")

    try:
        keepa_info, raw_series = fetch_product_by_isbn(
            resolved_isbn,
            marketplace,
            api_key=settings.keepa_api_key,
        )
    except KeepaProductNotFoundError as exc:
        raise PipelineError(str(exc)) from exc
    except KeepaNoSalesRankError as exc:
        raise PipelineError(str(exc)) from exc
    except KeepaError as exc:
        raise PipelineError(str(exc)) from exc

    points = filter_and_resample_daily(raw_series, start_date, end_date)
    if not points:
        raise PipelineError(
            "No hay histórico de BSR en el rango de fechas seleccionado. "
            "Prueba ampliar el periodo o verificar el marketplace."
        )

    summary = summarize_bsr_series(points)

    try:
        estimate = estimate_sales(
            settings=settings,
            book=book,
            marketplace_label=marketplace.label,
            keepa=keepa_info,
            points=points,
            summary=summary,
            date_start=start_date.isoformat(),
            date_end=end_date.isoformat(),
        )
    except LlmEstimatorError as exc:
        raise PipelineError(str(exc)) from exc

    return PipelineResult(
        book=book,
        marketplace_code=marketplace.code,
        marketplace_label=marketplace.label,
        keepa=keepa_info,
        bsr_series=points,
        summary=summary,
        estimate=estimate,
        date_range_start=start_date,
        date_range_end=end_date,
    )


def resolve_book_by_title(
    settings: Settings,
    title: str,
    marketplace_code: str,
):
    marketplace = get_marketplace(marketplace_code)
    return search_by_title(
        title,
        marketplace,
        api_key=settings.google_books_api_key,
    )

import time
from datetime import datetime, timezone

import httpx

from book_sales_tracker.marketplace import MarketplaceConfig
from book_sales_tracker.models import KeepaProductInfo

KEEPA_BASE = "https://api.keepa.com/product"
KEEPA_EPOCH_OFFSET_MINUTES = 21564000
MAX_RETRIES = 3


class KeepaError(Exception):
    pass


class KeepaProductNotFoundError(KeepaError):
    pass


class KeepaNoSalesRankError(KeepaError):
    pass


def keepa_minutes_to_datetime(keepa_minutes: int) -> datetime:
    timestamp_ms = (keepa_minutes + KEEPA_EPOCH_OFFSET_MINUTES) * 60_000
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def _parse_sales_rank_series(raw_series: list[int]) -> list[tuple[datetime, int]]:
    points: list[tuple[datetime, int]] = []
    for index in range(0, len(raw_series) - 1, 2):
        keepa_time = raw_series[index]
        rank = raw_series[index + 1]
        if rank is None or rank < 0:
            continue
        points.append((keepa_minutes_to_datetime(keepa_time), int(rank)))
    return points


def _extract_bsr_series(product: dict) -> tuple[list[tuple[datetime, int]], int | None]:
    sales_rank_reference = product.get("salesRankReference")
    if sales_rank_reference in (-1, -2, None):
        raise KeepaNoSalesRankError(
            "Este producto no tiene sales rank disponible en la categoría principal."
        )

    category_id = int(sales_rank_reference)
    csv_data = product.get("csv") or []
    sales_ranks = product.get("salesRanks") or {}
    category_key = str(category_id)

    candidates: list[tuple[str, list[tuple[datetime, int]]]] = []

    if len(csv_data) > 3 and csv_data[3]:
        candidates.append(("csv_sales", _parse_sales_rank_series(csv_data[3])))

    if category_key in sales_ranks and sales_ranks[category_key]:
        candidates.append(
            ("sales_ranks_ref", _parse_sales_rank_series(sales_ranks[category_key]))
        )

    if not candidates:
        raise KeepaNoSalesRankError(
            "No se encontró histórico de BSR para la categoría principal del producto."
        )

    _, best_series = min(
        candidates,
        key=lambda item: item[1][0][0]
        if item[1]
        else datetime.max.replace(tzinfo=timezone.utc),
    )
    if not best_series:
        raise KeepaNoSalesRankError("El histórico de BSR está vacío.")

    return best_series, category_id


def fetch_product_by_isbn(
    isbn: str,
    marketplace: MarketplaceConfig,
    api_key: str,
) -> tuple[KeepaProductInfo, list[tuple[datetime, int]]]:
    params = {
        "key": api_key,
        "domain": marketplace.keepa_domain_id,
        "code": isbn,
        "history": 1,
    }

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.get(KEEPA_BASE, params=params)
            response.raise_for_status()
            payload = response.json()
            break
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code
            if status in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            if status == 429:
                raise KeepaError(
                    "Keepa ha limitado la petición (429). Espera unos segundos e inténtalo de nuevo."
                ) from exc
            raise KeepaError(f"Keepa devolvió HTTP {status}.") from exc
        except httpx.RequestError as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise KeepaError(f"No se pudo conectar con Keepa: {exc}") from exc
    else:
        raise KeepaError(f"Keepa no respondió tras varios intentos: {last_error}")

    if payload.get("error"):
        raise KeepaError(f"Keepa API error: {payload['error']}")

    products = payload.get("products") or []
    if not products:
        raise KeepaProductNotFoundError(
            f"Keepa no encontró el ISBN {isbn} en {marketplace.label}."
        )

    product = products[0]
    if not product.get("asin"):
        raise KeepaProductNotFoundError(
            f"Keepa no pudo resolver el ISBN {isbn} a un ASIN en {marketplace.label}."
        )

    bsr_series, category_id = _extract_bsr_series(product)
    if not bsr_series:
        raise KeepaNoSalesRankError("El producto no tiene histórico de BSR disponible.")

    listed_since = (
        keepa_minutes_to_datetime(product["listedSince"])
        if product.get("listedSince")
        else None
    )
    tracking_since = (
        keepa_minutes_to_datetime(product["trackingSince"])
        if product.get("trackingSince")
        else None
    )

    info = KeepaProductInfo(
        asin=product["asin"],
        title=product.get("title"),
        category_id=category_id,
        sales_rank_reference=product.get("salesRankReference"),
        listed_since=listed_since,
        tracking_since=tracking_since,
        bsr_available_from=bsr_series[0][0],
        bsr_available_to=bsr_series[-1][0],
    )
    return info, bsr_series

from datetime import datetime, timezone

import httpx

from book_sales_tracker.marketplace import MarketplaceConfig
from book_sales_tracker.models import KeepaProductInfo

KEEPA_BASE = "https://api.keepa.com/product"
KEEPA_EPOCH_OFFSET_MINUTES = 21564000


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
    sales_ranks = product.get("salesRanks") or {}
    category_key = str(category_id)

    if category_key in sales_ranks and sales_ranks[category_key]:
        return _parse_sales_rank_series(sales_ranks[category_key]), category_id

    csv_data = product.get("csv") or []
    if len(csv_data) > 3 and csv_data[3]:
        return _parse_sales_rank_series(csv_data[3]), category_id

    raise KeepaNoSalesRankError(
        "No se encontró histórico de BSR para la categoría principal del producto."
    )


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

    with httpx.Client(timeout=60.0) as client:
        response = client.get(KEEPA_BASE, params=params)
        response.raise_for_status()
        payload = response.json()

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

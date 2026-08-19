from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

KEEPA_EPOCH_OFFSET_MINUTES = 21564000


def keepa_minutes_to_datetime(keepa_minutes: int) -> datetime:
    timestamp_ms = (keepa_minutes + KEEPA_EPOCH_OFFSET_MINUTES) * 60_000
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def _last_valid_from_csv_series(raw_series: list[int] | None) -> int | None:
    if not raw_series:
        return None
    last_valid: int | None = None
    for index in range(0, len(raw_series) - 1, 2):
        value = raw_series[index + 1]
        if value is not None and value >= 0:
            last_valid = int(value)
    return last_valid


def extract_sales_rank(product: dict[str, Any]) -> int | None:
    sales_rank_reference = product.get("salesRankReference")
    if sales_rank_reference in (-1, -2, None):
        return None

    category_key = str(int(sales_rank_reference))
    sales_ranks = product.get("salesRanks") or {}
    rank_from_category = _last_valid_from_csv_series(sales_ranks.get(category_key))

    csv_data = product.get("csv") or []
    rank_from_csv = _last_valid_from_csv_series(csv_data[3] if len(csv_data) > 3 else None)

    if rank_from_csv is not None:
        return rank_from_csv
    return rank_from_category


def extract_price_cents(product: dict[str, Any]) -> int | None:
    csv_data = product.get("csv") or []
    for index in (0, 1):
        if len(csv_data) <= index:
            continue
        price = _last_valid_from_csv_series(csv_data[index])
        if price is not None and price > 0:
            return price
    return None

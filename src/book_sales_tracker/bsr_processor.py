from datetime import date, datetime, time, timezone

from book_sales_tracker.models import BsrPoint, BsrSummary, RankTier


def classify_bsr(rank: int) -> RankTier:
    if rank <= 10:
        return RankTier.TOP_10
    if rank <= 100:
        return RankTier.TOP_100
    if rank <= 500:
        return RankTier.TOP_500
    if rank <= 2_000:
        return RankTier.TOP_2K
    if rank <= 10_000:
        return RankTier.TOP_10K
    if rank <= 50_000:
        return RankTier.TOP_50K
    return RankTier.LONG_TAIL


def _to_utc_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def filter_and_resample_daily(
    series: list[tuple[datetime, int]],
    start: date | datetime,
    end: date | datetime,
) -> list[BsrPoint]:
    start_dt = _to_utc_datetime(start)
    end_dt = _to_utc_datetime(end)
    if end_dt.time() == time.min:
        end_dt = datetime.combine(end_dt.date(), time.max, tzinfo=timezone.utc)

    filtered = [
        (timestamp, rank)
        for timestamp, rank in series
        if start_dt <= timestamp <= end_dt and rank > 0
    ]
    if not filtered:
        return []

    daily: dict[date, tuple[datetime, int]] = {}
    for timestamp, rank in filtered:
        day = timestamp.date()
        existing = daily.get(day)
        if existing is None or timestamp >= existing[0]:
            daily[day] = (timestamp, rank)

    points: list[BsrPoint] = []
    for day in sorted(daily):
        timestamp, rank = daily[day]
        tier = classify_bsr(rank)
        points.append(BsrPoint(timestamp=timestamp, bsr=rank, tier=tier))
    return points


def summarize_bsr_series(points: list[BsrPoint]) -> BsrSummary:
    if not points:
        return BsrSummary(tier_distribution={})

    tier_counts: dict[str, int] = {}
    for point in points:
        label = point.tier.label_es
        tier_counts[label] = tier_counts.get(label, 0) + 1

    total = len(points)
    tier_distribution = {
        label: round(count / total * 100, 1) for label, count in tier_counts.items()
    }

    tier_changes = sum(
        1 for index in range(1, len(points)) if points[index].tier != points[index - 1].tier
    )

    bsr_values = [point.bsr for point in points]
    best_tier = min(points, key=lambda point: point.tier.value).tier

    return BsrSummary(
        tier_distribution=tier_distribution,
        min_bsr=min(bsr_values),
        max_bsr=max(bsr_values),
        best_tier=best_tier,
        start_tier=points[0].tier,
        end_tier=points[-1].tier,
        tier_changes=tier_changes,
        total_days=total,
    )

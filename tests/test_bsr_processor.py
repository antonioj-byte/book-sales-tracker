from datetime import date, datetime, timezone

from book_sales_tracker.bsr_processor import (
    classify_bsr,
    filter_and_resample_daily,
    summarize_bsr_series,
)
from book_sales_tracker.llm_estimator import _parse_sections
from book_sales_tracker.models import RankTier


def test_classify_bsr_boundaries() -> None:
    assert classify_bsr(1) == RankTier.TOP_10
    assert classify_bsr(10) == RankTier.TOP_10
    assert classify_bsr(11) == RankTier.TOP_100
    assert classify_bsr(10_000) == RankTier.TOP_10K
    assert classify_bsr(10_001) == RankTier.TOP_50K
    assert classify_bsr(150_001) == RankTier.BEYOND_150K


def test_daily_resample_uses_last_point_of_day() -> None:
    series = [
        (datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc), 500),
        (datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc), 120),
        (datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc), 300),
    ]
    points = filter_and_resample_daily(series, date(2025, 1, 1), date(2025, 1, 2))
    assert len(points) == 2
    assert points[0].bsr == 120
    assert points[1].bsr == 300


def test_summary_counts_tier_changes() -> None:
    series = [
        (datetime(2025, 1, 1, tzinfo=timezone.utc), 50),
        (datetime(2025, 1, 2, tzinfo=timezone.utc), 4000),
        (datetime(2025, 1, 3, tzinfo=timezone.utc), 4500),
    ]
    points = filter_and_resample_daily(series, date(2025, 1, 1), date(2025, 1, 3))
    summary = summarize_bsr_series(points)
    assert summary.tier_changes == 1
    assert summary.total_days == 3


def test_parse_llm_sections() -> None:
    text = """## Rango estimado
10–30 unidades/semana

## Nivel de confianza
medio — datos limitados

## Explicación
El BSR se mantuvo en tramos medios."""
    parsed = _parse_sections(text)
    assert "10–30" in parsed.range_text
    assert "medio" in parsed.confidence
    assert "BSR" in parsed.explanation

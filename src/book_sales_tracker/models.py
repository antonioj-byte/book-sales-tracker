from datetime import date, datetime
from enum import IntEnum

from pydantic import BaseModel, Field


class RankTier(IntEnum):
    TOP_10 = 1
    TOP_100 = 2
    TOP_500 = 3
    TOP_1K = 4
    TOP_5K = 5
    TOP_10K = 6
    TOP_50K = 7
    TOP_100K = 8
    TOP_150K = 9
    BEYOND_150K = 10

    @property
    def label_es(self) -> str:
        labels = {
            RankTier.TOP_10: "Top 10",
            RankTier.TOP_100: "Top 100",
            RankTier.TOP_500: "Top 500",
            RankTier.TOP_1K: "Top 1.000",
            RankTier.TOP_5K: "Top 5.000",
            RankTier.TOP_10K: "Top 10.000",
            RankTier.TOP_50K: "Top 50.000",
            RankTier.TOP_100K: "Top 100.000",
            RankTier.TOP_150K: "Top 150.000",
            RankTier.BEYOND_150K: "Más de 150.000",
        }
        return labels[self]


class BookMetadata(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    publisher: str | None = None
    published_date: str | None = None
    categories: list[str] = Field(default_factory=list)
    isbn_10: str | None = None
    isbn_13: str | None = None
    google_books_id: str | None = None
    thumbnail_url: str | None = None


class BookSearchResult(BaseModel):
    metadata: BookMetadata
    display_label: str


class BsrPoint(BaseModel):
    timestamp: datetime
    bsr: int
    tier: RankTier

    @property
    def tier_label(self) -> str:
        return self.tier.label_es


class BsrSummary(BaseModel):
    tier_distribution: dict[str, float]
    min_bsr: int | None = None
    max_bsr: int | None = None
    best_tier: RankTier | None = None
    start_tier: RankTier | None = None
    end_tier: RankTier | None = None
    tier_changes: int = 0
    total_days: int = 0


class KeepaProductInfo(BaseModel):
    asin: str
    title: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    sales_rank_reference: int | None = None


class SalesEstimate(BaseModel):
    range_text: str
    confidence: str
    explanation: str
    raw_response: str


class PipelineResult(BaseModel):
    book: BookMetadata
    marketplace_code: str
    marketplace_label: str
    keepa: KeepaProductInfo
    bsr_series: list[BsrPoint]
    summary: BsrSummary
    estimate: SalesEstimate
    date_range_start: date
    date_range_end: date

from datetime import date, datetime
from enum import IntEnum

from pydantic import BaseModel, Field


class RankTier(IntEnum):
    TOP_10 = 1
    TOP_100 = 2
    TOP_500 = 3
    TOP_2K = 4
    TOP_10K = 5
    TOP_50K = 6
    LONG_TAIL = 7

    @property
    def label_es(self) -> str:
        labels = {
            RankTier.TOP_10: "Top 10",
            RankTier.TOP_100: "Top 100",
            RankTier.TOP_500: "Top 500",
            RankTier.TOP_2K: "Top 2.000",
            RankTier.TOP_10K: "Top 10.000",
            RankTier.TOP_50K: "Top 50.000",
            RankTier.LONG_TAIL: "Cola larga",
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


class PublisherSuggestion(BaseModel):
    name: str
    volume_count: int
    sample_titles: list[str] = Field(default_factory=list)
    match_score: float = 0.0


class PublisherCatalogResult(BaseModel):
    publisher_confirmed: str
    books: list[BookMetadata] = Field(default_factory=list)
    volumes_scanned: int = 0
    matched_publisher: int = 0
    in_date_range: int = 0
    with_isbn: int = 0
    queries_tried: list[str] = Field(default_factory=list)


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
    listed_since: datetime | None = None
    tracking_since: datetime | None = None
    bsr_available_from: datetime | None = None
    bsr_available_to: datetime | None = None


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

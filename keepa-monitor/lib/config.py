from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
import os

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DB_DIR = ROOT_DIR / "db"
LOGS_DIR = ROOT_DIR / "logs"
REPORTS_DIR = ROOT_DIR / "reports"
DEFAULT_DB_PATH = DB_DIR / "keepa_monitor.db"

TRACKED_ASINS_CSV = CONFIG_DIR / "tracked_asins.csv"
CATEGORIES_CSV = CONFIG_DIR / "categories.csv"


def _load_env_files() -> None:
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR.parent / ".env", override=False)


@dataclass(frozen=True)
class MonitorSettings:
    db_path: Path
    default_keepa_domain: int
    max_tokens_per_run: int
    category_tree_refresh_days: int
    best_sellers_top_n: int
    delta_threshold_pct: float
    position_move_threshold: int
    lookback_days: tuple[int, ...]
    report_days: int


@dataclass(frozen=True)
class FetchSettings(MonitorSettings):
    keepa_api_key: str


def _build_monitor_settings(db_path: Path | None) -> MonitorSettings:
    lookback_raw = os.getenv("LOOKBACK_DAYS", "7,30")
    lookback_days = tuple(int(part.strip()) for part in lookback_raw.split(",") if part.strip())
    return MonitorSettings(
        db_path=db_path or DEFAULT_DB_PATH,
        default_keepa_domain=int(os.getenv("DEFAULT_KEEPA_DOMAIN", "9")),
        max_tokens_per_run=int(os.getenv("MAX_TOKENS_PER_RUN", "150")),
        category_tree_refresh_days=int(os.getenv("CATEGORY_TREE_REFRESH_DAYS", "30")),
        best_sellers_top_n=int(os.getenv("BEST_SELLERS_TOP_N", "100")),
        delta_threshold_pct=float(os.getenv("DELTA_THRESHOLD_PCT", "80")),
        position_move_threshold=int(os.getenv("POSITION_MOVE_THRESHOLD", "30")),
        lookback_days=lookback_days or (7, 30),
        report_days=int(os.getenv("REPORT_DAYS", "7")),
    )


@lru_cache
def get_monitor_settings(db_path: Path | None = None) -> MonitorSettings:
    _load_env_files()
    return _build_monitor_settings(db_path)


@lru_cache
def get_fetch_settings(db_path: Path | None = None) -> FetchSettings:
    _load_env_files()
    api_key = os.getenv("KEEPA_API_KEY", "").strip()
    if not api_key:
        raise ValueError("KEEPA_API_KEY no configurada en keepa-monitor/.env o .env raíz")
    base = _build_monitor_settings(db_path)
    return FetchSettings(keepa_api_key=api_key, **base.__dict__)

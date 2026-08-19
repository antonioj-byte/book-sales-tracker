from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
import os

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DB_DIR = ROOT_DIR / "db"
LOGS_DIR = ROOT_DIR / "logs"
DEFAULT_DB_PATH = DB_DIR / "keepa_monitor.db"

TRACKED_ASINS_CSV = CONFIG_DIR / "tracked_asins.csv"
CATEGORIES_CSV = CONFIG_DIR / "categories.csv"


def _load_env_files() -> None:
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR.parent / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    keepa_api_key: str
    max_tokens_per_run: int
    default_keepa_domain: int
    category_tree_refresh_days: int
    best_sellers_top_n: int
    db_path: Path


@lru_cache
def get_settings(db_path: Path | None = None) -> Settings:
    _load_env_files()
    api_key = os.getenv("KEEPA_API_KEY", "").strip()
    if not api_key:
        raise ValueError("KEEPA_API_KEY no configurada en keepa-monitor/.env o .env raíz")

    return Settings(
        keepa_api_key=api_key,
        max_tokens_per_run=int(os.getenv("MAX_TOKENS_PER_RUN", "150")),
        default_keepa_domain=int(os.getenv("DEFAULT_KEEPA_DOMAIN", "9")),
        category_tree_refresh_days=int(os.getenv("CATEGORY_TREE_REFRESH_DAYS", "30")),
        best_sellers_top_n=int(os.getenv("BEST_SELLERS_TOP_N", "100")),
        db_path=db_path or DEFAULT_DB_PATH,
    )

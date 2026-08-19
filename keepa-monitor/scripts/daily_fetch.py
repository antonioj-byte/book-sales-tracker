from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from lib.config import (  # noqa: E402
    CATEGORIES_CSV,
    LOGS_DIR,
    TRACKED_ASINS_CSV,
    get_settings,
)
from lib.db import (  # noqa: E402
    category_tree_last_updated,
    connect,
    create_fetch_run,
    finish_fetch_run,
    init_schema,
    insert_absolute_snapshot,
    insert_relative_snapshot,
    upsert_category,
)
from lib.extractors import extract_price_cents, extract_sales_rank  # noqa: E402
from lib.keepa_client import (  # noqa: E402
    TOKEN_COST_BEST_SELLERS,
    TOKEN_COST_CATEGORY_LOOKUP,
    TOKEN_COST_PRODUCT,
    TokenBudget,
    TokenBudgetExceeded,
    create_keepa_client,
    domain_to_keepa,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrackedAsin:
    asin: str
    editorial: str
    tipo: str
    nombre_libro: str


@dataclass(frozen=True)
class TrackedCategory:
    categoria_id: str
    nombre: str
    mercado: int


def setup_logging(log_file: Path) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def load_tracked_asins() -> list[TrackedAsin]:
    df = pd.read_csv(TRACKED_ASINS_CSV, dtype=str).fillna("")
    rows: list[TrackedAsin] = []
    for _, record in df.iterrows():
        tipo = record["tipo"].strip().lower()
        if tipo not in {"propio", "escauteado"}:
            raise ValueError(f"tipo inválido en tracked_asins.csv: {record['tipo']}")
        rows.append(
            TrackedAsin(
                asin=record["asin"].strip(),
                editorial=record["editorial"].strip(),
                tipo=tipo,
                nombre_libro=record["nombre_libro"].strip(),
            )
        )
    return rows


def load_categories() -> list[TrackedCategory]:
    df = pd.read_csv(CATEGORIES_CSV, dtype={"categoria_id": str, "nombre": str})
    rows: list[TrackedCategory] = []
    for _, record in df.iterrows():
        rows.append(
            TrackedCategory(
                categoria_id=str(record["categoria_id"]).strip(),
                nombre=str(record["nombre"]).strip(),
                mercado=int(record["mercado"]),
            )
        )
    return rows


def should_refresh_category_tree(
    conn,
    domain_id: int,
    refresh_days: int,
    now: datetime,
) -> bool:
    last_update = category_tree_last_updated(conn, domain_id)
    if not last_update:
        return True
    last_dt = datetime.fromisoformat(last_update)
    return (now - last_dt).days >= refresh_days


def refresh_category_tree(
    api,
    conn,
    categories: list[TrackedCategory],
    budget: TokenBudget,
    now_iso: str,
) -> None:
    seen: set[tuple[str, int]] = set()
    for category in categories:
        key = (category.categoria_id, category.mercado)
        if key in seen:
            continue
        seen.add(key)

        budget.check_budget(TOKEN_COST_CATEGORY_LOOKUP, f"category_lookup:{category.categoria_id}")
        lookup = api.category_lookup(
            int(category.categoria_id),
            include_parents=True,
            domain=domain_to_keepa(category.mercado),
        )
        budget.after_call(api, f"category_lookup:{category.categoria_id}", TOKEN_COST_CATEGORY_LOOKUP)

        for cat_id, cat_data in lookup.items():
            upsert_category(
                conn,
                {
                    "category_id": str(cat_id),
                    "domain_id": category.mercado,
                    "name": cat_data.get("name") or category.nombre,
                    "parent_id": str(cat_data["parent"]) if cat_data.get("parent") else None,
                    "product_count": cat_data.get("productCount"),
                    "updated_at": now_iso,
                },
            )
    conn.commit()


def fetch_relative_snapshots(
    api,
    conn,
    tracked_asins: list[TrackedAsin],
    domain_id: int,
    snapshot_date: str,
    fetched_at: str,
    budget: TokenBudget,
) -> int:
    if not tracked_asins:
        return 0

    asins = [row.asin for row in tracked_asins]
    estimated = TOKEN_COST_PRODUCT * len(asins)
    budget.check_budget(estimated, "query:relative_asins")

    products = api.query(
        asins,
        history=True,
        days=2,
        domain=domain_to_keepa(domain_id),
        progress_bar=False,
    )
    budget.after_call(api, "query:relative_asins", estimated)

    products_by_asin = {product["asin"]: product for product in products}
    for row in tracked_asins:
        product = products_by_asin.get(row.asin)
        sales_rank = extract_sales_rank(product) if product else None
        price_cents = extract_price_cents(product) if product else None
        insert_relative_snapshot(
            conn,
            {
                "snapshot_date": snapshot_date,
                "domain_id": domain_id,
                "asin": row.asin,
                "editorial": row.editorial,
                "tipo": row.tipo,
                "nombre_libro": row.nombre_libro,
                "sales_rank": sales_rank,
                "price_cents": price_cents,
                "fetched_at": fetched_at,
            },
        )
    conn.commit()
    return len(asins)


def fetch_absolute_snapshots(
    api,
    conn,
    categories: list[TrackedCategory],
    snapshot_date: str,
    fetched_at: str,
    top_n: int,
    budget: TokenBudget,
) -> int:
    queried = 0
    for category in categories:
        budget.check_budget(TOKEN_COST_BEST_SELLERS, f"best_sellers:{category.categoria_id}")
        asins = api.best_sellers_query(
            category.categoria_id,
            domain=domain_to_keepa(category.mercado),
        )
        budget.after_call(api, f"best_sellers:{category.categoria_id}", TOKEN_COST_BEST_SELLERS)
        queried += 1

        for position, asin in enumerate(asins[:top_n], start=1):
            insert_absolute_snapshot(
                conn,
                {
                    "snapshot_date": snapshot_date,
                    "domain_id": category.mercado,
                    "category_id": category.categoria_id,
                    "category_name": category.nombre,
                    "rank_position": position,
                    "asin": asin,
                    "fetched_at": fetched_at,
                },
            )
    conn.commit()
    return queried


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch diario Keepa → SQLite")
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--skip-category-tree", action="store_true")
    args = parser.parse_args()

    settings = get_settings(db_path=args.db_path)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    snapshot_date = now.date().isoformat()
    log_file = LOGS_DIR / f"fetch_{snapshot_date}.log"
    setup_logging(log_file)

    tracked_asins = load_tracked_asins()
    categories = load_categories()
    conn = connect(settings.db_path)
    init_schema(conn)

    api = create_keepa_client(settings.keepa_api_key)
    budget = TokenBudget.from_api(api, settings.max_tokens_per_run)
    run_id = create_fetch_run(conn, now_iso, budget.tokens_before)

    asins_queried = 0
    categories_queried = 0
    status = "ok"
    details: dict = {"calls": [], "log_file": str(log_file)}

    try:
        if not args.skip_category_tree:
            domains = {category.mercado for category in categories}
            domains.add(settings.default_keepa_domain)
            for domain_id in domains:
                if should_refresh_category_tree(
                    conn,
                    domain_id,
                    settings.category_tree_refresh_days,
                    now,
                ):
                    logger.info("Actualizando category_tree para domain_id=%s", domain_id)
                    refresh_category_tree(api, conn, categories, budget, now_iso)
                else:
                    logger.info("category_tree al día para domain_id=%s", domain_id)

        asins_queried = fetch_relative_snapshots(
            api,
            conn,
            tracked_asins,
            settings.default_keepa_domain,
            snapshot_date,
            now_iso,
            budget,
        )
        categories_queried = fetch_absolute_snapshots(
            api,
            conn,
            categories,
            snapshot_date,
            now_iso,
            settings.best_sellers_top_n,
            budget,
        )
        details["calls"] = budget.calls
        logger.info(
            "Fetch completado | ASINs=%s categorías=%s tokens_usados=%s restantes=%s",
            asins_queried,
            categories_queried,
            budget.tokens_spent,
            api.tokens_left,
        )
    except TokenBudgetExceeded as exc:
        status = "aborted"
        details["error"] = str(exc)
        logger.error("Fetch abortado: %s", exc)
    except Exception as exc:
        status = "error"
        details["error"] = str(exc)
        logger.exception("Fetch fallido: %s", exc)
        raise
    finally:
        finish_fetch_run(
            conn,
            run_id,
            finished_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            tokens_after=int(api.tokens_left),
            tokens_used=budget.tokens_spent,
            asins_queried=asins_queried,
            categories_queried=categories_queried,
            details=details,
        )
        conn.close()

    if status != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()

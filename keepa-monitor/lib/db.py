import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rank_snapshots_relative (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    domain_id INTEGER NOT NULL,
    asin TEXT NOT NULL,
    editorial TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('propio', 'escauteado')),
    nombre_libro TEXT NOT NULL,
    sales_rank INTEGER,
    price_cents INTEGER,
    fetched_at TEXT NOT NULL,
    UNIQUE (snapshot_date, domain_id, asin)
);

CREATE INDEX IF NOT EXISTS idx_relative_asin_date
    ON rank_snapshots_relative (asin, snapshot_date);

CREATE TABLE IF NOT EXISTS rank_snapshots_absolute (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    domain_id INTEGER NOT NULL,
    category_id TEXT NOT NULL,
    category_name TEXT NOT NULL,
    rank_position INTEGER NOT NULL CHECK (rank_position BETWEEN 1 AND 100),
    asin TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    UNIQUE (snapshot_date, domain_id, category_id, rank_position)
);

CREATE INDEX IF NOT EXISTS idx_absolute_cat_date
    ON rank_snapshots_absolute (snapshot_date, domain_id, category_id);

CREATE TABLE IF NOT EXISTS category_tree (
    category_id TEXT NOT NULL,
    domain_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    parent_id TEXT,
    product_count INTEGER,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (category_id, domain_id)
);

CREATE TABLE IF NOT EXISTS fetch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_started_at TEXT NOT NULL,
    run_finished_at TEXT,
    status TEXT NOT NULL,
    tokens_before INTEGER NOT NULL,
    tokens_after INTEGER,
    tokens_used INTEGER,
    asins_queried INTEGER NOT NULL DEFAULT 0,
    categories_queried INTEGER NOT NULL DEFAULT 0,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_date TEXT NOT NULL,
    module TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    domain_id INTEGER,
    asin TEXT,
    category_id TEXT,
    rank_before INTEGER,
    rank_after INTEGER,
    delta_pct REAL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def insert_relative_snapshot(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO rank_snapshots_relative (
            snapshot_date, domain_id, asin, editorial, tipo, nombre_libro,
            sales_rank, price_cents, fetched_at
        ) VALUES (
            :snapshot_date, :domain_id, :asin, :editorial, :tipo, :nombre_libro,
            :sales_rank, :price_cents, :fetched_at
        )
        """,
        row,
    )


def insert_absolute_snapshot(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO rank_snapshots_absolute (
            snapshot_date, domain_id, category_id, category_name,
            rank_position, asin, fetched_at
        ) VALUES (
            :snapshot_date, :domain_id, :category_id, :category_name,
            :rank_position, :asin, :fetched_at
        )
        """,
        row,
    )


def upsert_category(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO category_tree (
            category_id, domain_id, name, parent_id, product_count, updated_at
        ) VALUES (
            :category_id, :domain_id, :name, :parent_id, :product_count, :updated_at
        )
        ON CONFLICT(category_id, domain_id) DO UPDATE SET
            name = excluded.name,
            parent_id = excluded.parent_id,
            product_count = excluded.product_count,
            updated_at = excluded.updated_at
        """,
        row,
    )


def create_fetch_run(conn: sqlite3.Connection, started_at: str, tokens_before: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO fetch_runs (run_started_at, status, tokens_before)
        VALUES (?, 'running', ?)
        """,
        (started_at, tokens_before),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_fetch_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    finished_at: str,
    status: str,
    tokens_after: int | None,
    tokens_used: int | None,
    asins_queried: int,
    categories_queried: int,
    details: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE fetch_runs SET
            run_finished_at = ?,
            status = ?,
            tokens_after = ?,
            tokens_used = ?,
            asins_queried = ?,
            categories_queried = ?,
            details_json = ?
        WHERE id = ?
        """,
        (
            finished_at,
            status,
            tokens_after,
            tokens_used,
            asins_queried,
            categories_queried,
            json.dumps(details, ensure_ascii=False),
            run_id,
        ),
    )
    conn.commit()


def category_tree_last_updated(conn: sqlite3.Connection, domain_id: int) -> str | None:
    row = conn.execute(
        "SELECT MAX(updated_at) AS last_update FROM category_tree WHERE domain_id = ?",
        (domain_id,),
    ).fetchone()
    if row and row["last_update"]:
        return str(row["last_update"])
    return None

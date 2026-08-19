from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MONITOR_DB = REPO_ROOT / "keepa-monitor" / "db" / "keepa_monitor.db"

DOMAIN_LABELS: dict[int, str] = {
    1: "Amazon.com",
    2: "Amazon.co.uk",
    3: "Amazon.de",
    4: "Amazon.fr",
    8: "Amazon.it",
    9: "Amazon.es",
}


@dataclass(frozen=True)
class RelativeSnapshot:
    snapshot_date: str
    domain_id: int
    asin: str
    editorial: str
    tipo: str
    nombre_libro: str
    sales_rank: int | None
    price_cents: int | None


@dataclass(frozen=True)
class AbsoluteRow:
    snapshot_date: str
    domain_id: int
    category_id: str
    category_name: str
    rank_position: int
    asin: str


def domain_label(domain_id: int) -> str:
    return DOMAIN_LABELS.get(domain_id, f"domain {domain_id}")


def db_exists(db_path: Path | None = None) -> bool:
    path = db_path or DEFAULT_MONITOR_DB
    return path.is_file()


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_MONITOR_DB
    if not path.is_file():
        raise FileNotFoundError(f"No se encontró la base del monitor: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def latest_snapshot_dates(conn: sqlite3.Connection) -> dict[str, str | None]:
    relative = conn.execute(
        "SELECT MAX(snapshot_date) FROM rank_snapshots_relative"
    ).fetchone()[0]
    absolute = conn.execute(
        "SELECT MAX(snapshot_date) FROM rank_snapshots_absolute"
    ).fetchone()[0]
    return {
        "relative": str(relative) if relative else None,
        "absolute": str(absolute) if absolute else None,
    }


def list_markets_with_data(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    rows = conn.execute(
        """
        SELECT DISTINCT domain_id FROM rank_snapshots_absolute
        UNION
        SELECT DISTINCT domain_id FROM rank_snapshots_relative
        ORDER BY domain_id
        """
    ).fetchall()
    return [(int(row["domain_id"]), domain_label(int(row["domain_id"]))) for row in rows]


def list_categories(conn: sqlite3.Connection, domain_id: int | None = None) -> list[dict]:
    query = """
        SELECT DISTINCT domain_id, category_id, category_name
        FROM rank_snapshots_absolute
    """
    params: list = []
    if domain_id is not None:
        query += " WHERE domain_id = ?"
        params.append(domain_id)
    query += " ORDER BY domain_id, category_name"
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def fetch_relative_history(conn: sqlite3.Connection) -> list[RelativeSnapshot]:
    rows = conn.execute(
        """
        SELECT snapshot_date, domain_id, asin, editorial, tipo, nombre_libro,
               sales_rank, price_cents
        FROM rank_snapshots_relative
        ORDER BY snapshot_date, tipo, nombre_libro
        """
    ).fetchall()
    return [
        RelativeSnapshot(
            snapshot_date=str(row["snapshot_date"]),
            domain_id=int(row["domain_id"]),
            asin=str(row["asin"]),
            editorial=str(row["editorial"]),
            tipo=str(row["tipo"]),
            nombre_libro=str(row["nombre_libro"]),
            sales_rank=row["sales_rank"],
            price_cents=row["price_cents"],
        )
        for row in rows
    ]


def relative_to_dataframe(snapshots: list[RelativeSnapshot]) -> pd.DataFrame:
    if not snapshots:
        return pd.DataFrame()
    records = [
        {
            "fecha": s.snapshot_date,
            "mercado": domain_label(s.domain_id),
            "domain_id": s.domain_id,
            "tipo": s.tipo,
            "libro": s.nombre_libro,
            "asin": s.asin,
            "editorial": s.editorial,
            "sales_rank": s.sales_rank,
            "precio_eur": round(s.price_cents / 100, 2) if s.price_cents else None,
        }
        for s in snapshots
    ]
    return pd.DataFrame(records)


def fetch_absolute_top(
    conn: sqlite3.Connection,
    *,
    domain_id: int,
    category_id: str,
    snapshot_date: str | None = None,
    limit: int = 100,
) -> list[AbsoluteRow]:
    if snapshot_date is None:
        snapshot_date = conn.execute(
            """
            SELECT MAX(snapshot_date) FROM rank_snapshots_absolute
            WHERE domain_id = ? AND category_id = ?
            """,
            (domain_id, category_id),
        ).fetchone()[0]
    if not snapshot_date:
        return []

    rows = conn.execute(
        """
        SELECT snapshot_date, domain_id, category_id, category_name,
               rank_position, asin
        FROM rank_snapshots_absolute
        WHERE snapshot_date = ? AND domain_id = ? AND category_id = ?
        ORDER BY rank_position
        LIMIT ?
        """,
        (snapshot_date, domain_id, category_id, limit),
    ).fetchall()
    return [
        AbsoluteRow(
            snapshot_date=str(row["snapshot_date"]),
            domain_id=int(row["domain_id"]),
            category_id=str(row["category_id"]),
            category_name=str(row["category_name"]),
            rank_position=int(row["rank_position"]),
            asin=str(row["asin"]),
        )
        for row in rows
    ]


def absolute_to_dataframe(rows: list[AbsoluteRow]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "posición": [r.rank_position for r in rows],
            "asin": [r.asin for r in rows],
            "fecha": [r.snapshot_date for r in rows],
        }
    )


def relative_comparison_summary(snapshots: list[RelativeSnapshot]) -> pd.DataFrame:
    if not snapshots:
        return pd.DataFrame()
    df = relative_to_dataframe(snapshots)
    if df.empty:
        return df

    summary_rows = []
    for (libro, asin, tipo), group in df.groupby(["libro", "asin", "tipo"]):
        group = group.sort_values("fecha")
        first = group.iloc[0]
        last = group.iloc[-1]
        rank_first = first["sales_rank"]
        rank_last = last["sales_rank"]
        delta_pct = None
        if rank_first and rank_last and rank_first > 0:
            delta_pct = round((rank_last - rank_first) / rank_first * 100, 1)
        summary_rows.append(
            {
                "tipo": tipo,
                "libro": libro,
                "asin": asin,
                "mercado": last["mercado"],
                "rank_inicio": rank_first,
                "rank_último": rank_last,
                "delta_%": delta_pct,
                "días_datos": len(group),
            }
        )
    return pd.DataFrame(summary_rows).sort_values("tipo")


def detect_jumps_for_ui(
    conn: sqlite3.Connection,
    *,
    domain_ids: tuple[int, ...],
    lookback_days: int = 7,
    min_severity: str = "all",
):
    keepa_root = REPO_ROOT / "keepa-monitor"
    import sys

    sys.path.insert(0, str(keepa_root))
    from lib.config import get_monitor_settings
    from lib.jumps import JumpSeverity, detect_category_jumps

    settings = get_monitor_settings(db_path=DEFAULT_MONITOR_DB)
    severity = None if min_severity == "all" else JumpSeverity(min_severity)
    return detect_category_jumps(
        conn,
        settings,
        lookback_days=lookback_days,
        domain_ids=domain_ids,
        min_severity=severity,
    )

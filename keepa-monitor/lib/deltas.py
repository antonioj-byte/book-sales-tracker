from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from lib.config import MonitorSettings
from lib.db import delete_alerts_for_date, insert_alert


@dataclass(frozen=True)
class RelativeRow:
    asin: str
    editorial: str
    tipo: str
    nombre_libro: str
    domain_id: int
    rank_today: int | None
    rank_before: int | None
    lookback_days: int
    delta_pct: float | None


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _subtract_days(base: str, days: int) -> str:
    return (_parse_date(base) - timedelta(days=days)).isoformat()


def compute_delta_pct(rank_today: int, rank_before: int) -> float:
    if rank_before <= 0:
        raise ValueError("rank_before debe ser positivo")
    return (rank_today - rank_before) / rank_before * 100.0


def fetch_relative_rows(
    conn,
    snapshot_today: str,
    lookback_days: int,
) -> list[RelativeRow]:
    snapshot_before = conn.execute(
        """
        SELECT MAX(snapshot_date) FROM rank_snapshots_relative
        WHERE snapshot_date <= ?
        """,
        (_subtract_days(snapshot_today, lookback_days),),
    ).fetchone()[0]
    if not snapshot_before or snapshot_before == snapshot_today:
        return []

    rows = conn.execute(
        """
        SELECT
            t.asin, t.editorial, t.tipo, t.nombre_libro, t.domain_id,
            t.sales_rank AS rank_today,
            b.sales_rank AS rank_before
        FROM rank_snapshots_relative t
        JOIN rank_snapshots_relative b
          ON t.asin = b.asin AND t.domain_id = b.domain_id
        WHERE t.snapshot_date = ? AND b.snapshot_date = ?
        """,
        (snapshot_today, snapshot_before),
    ).fetchall()

    result: list[RelativeRow] = []
    for row in rows:
        rank_today = row["rank_today"]
        rank_before = row["rank_before"]
        delta = None
        if rank_today is not None and rank_before is not None and rank_before > 0:
            delta = compute_delta_pct(rank_today, rank_before)
        result.append(
            RelativeRow(
                asin=row["asin"],
                editorial=row["editorial"],
                tipo=row["tipo"],
                nombre_libro=row["nombre_libro"],
                domain_id=row["domain_id"],
                rank_today=rank_today,
                rank_before=rank_before,
                lookback_days=lookback_days,
                delta_pct=delta,
            )
        )
    return result


def build_relative_alerts(
    rows: list[RelativeRow],
    settings: MonitorSettings,
    alert_date: str,
    created_at: str,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for row in rows:
        if row.delta_pct is None or row.rank_today is None or row.rank_before is None:
            continue
        if abs(row.delta_pct) < settings.delta_threshold_pct:
            continue

        direction = "mejoró" if row.delta_pct < 0 else "empeoró"
        message = (
            f"[{row.tipo.upper()}] {row.nombre_libro} ({row.asin}) {direction} de rank "
            f"{row.rank_before:,} a {row.rank_today:,} ({row.delta_pct:+.1f}%) en "
            f"{row.lookback_days} días [{row.editorial}]"
        )
        alerts.append(
            {
                "alert_date": alert_date,
                "module": "relative",
                "alert_type": f"rank_delta_{row.lookback_days}d",
                "domain_id": row.domain_id,
                "asin": row.asin,
                "category_id": None,
                "rank_before": row.rank_before,
                "rank_after": row.rank_today,
                "delta_pct": row.delta_pct,
                "message": message,
                "created_at": created_at,
            }
        )
    return alerts


def fetch_absolute_top100(conn, snapshot_date: str, domain_id: int, category_id: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT asin, rank_position FROM rank_snapshots_absolute
        WHERE snapshot_date = ? AND domain_id = ? AND category_id = ?
        """,
        (snapshot_date, domain_id, category_id),
    ).fetchall()
    return {row["asin"]: row["rank_position"] for row in rows}


def build_absolute_alerts(
    conn,
    settings: MonitorSettings,
    snapshot_today: str,
    lookback_days: int,
    alert_date: str,
    created_at: str,
) -> list[dict[str, Any]]:
    snapshot_before = conn.execute(
        """
        SELECT MAX(snapshot_date) FROM rank_snapshots_absolute
        WHERE snapshot_date <= ?
        """,
        (_subtract_days(snapshot_today, lookback_days),),
    ).fetchone()[0]
    if not snapshot_before or snapshot_before == snapshot_today:
        return []

    categories = conn.execute(
        """
        SELECT DISTINCT domain_id, category_id, category_name
        FROM rank_snapshots_absolute
        WHERE snapshot_date = ?
        """,
        (snapshot_today,),
    ).fetchall()

    alerts: list[dict[str, Any]] = []
    for cat in categories:
        today_map = fetch_absolute_top100(
            conn, snapshot_today, cat["domain_id"], cat["category_id"]
        )
        before_map = fetch_absolute_top100(
            conn, snapshot_before, cat["domain_id"], cat["category_id"]
        )
        today_asins = set(today_map)
        before_asins = set(before_map)

        for asin in sorted(today_asins - before_asins):
            alerts.append(
                {
                    "alert_date": alert_date,
                    "module": "absolute",
                    "alert_type": "entered_top100",
                    "domain_id": cat["domain_id"],
                    "asin": asin,
                    "category_id": cat["category_id"],
                    "rank_before": None,
                    "rank_after": today_map[asin],
                    "delta_pct": None,
                    "message": (
                        f"Entró al top 100 en {cat['category_name']} (mercado {cat['domain_id']}): "
                        f"ASIN {asin} en posición {today_map[asin]} (vs hace {lookback_days} días)"
                    ),
                    "created_at": created_at,
                }
            )

        for asin in sorted(before_asins - today_asins):
            alerts.append(
                {
                    "alert_date": alert_date,
                    "module": "absolute",
                    "alert_type": "left_top100",
                    "domain_id": cat["domain_id"],
                    "asin": asin,
                    "category_id": cat["category_id"],
                    "rank_before": before_map[asin],
                    "rank_after": None,
                    "delta_pct": None,
                    "message": (
                        f"Salió del top 100 en {cat['category_name']} (mercado {cat['domain_id']}): "
                        f"ASIN {asin} (estaba en posición {before_map[asin]} hace {lookback_days} días)"
                    ),
                    "created_at": created_at,
                }
            )

        for asin in sorted(today_asins & before_asins):
            pos_today = today_map[asin]
            pos_before = before_map[asin]
            move = pos_today - pos_before
            if abs(move) >= settings.position_move_threshold:
                direction = "subió" if move < 0 else "bajó"
                alerts.append(
                    {
                        "alert_date": alert_date,
                        "module": "absolute",
                        "alert_type": "position_move",
                        "domain_id": cat["domain_id"],
                        "asin": asin,
                        "category_id": cat["category_id"],
                        "rank_before": pos_before,
                        "rank_after": pos_today,
                        "delta_pct": None,
                        "message": (
                            f"Se movió {abs(move)} posiciones en {cat['category_name']} "
                            f"(mercado {cat['domain_id']}): ASIN {asin} {direction} de "
                            f"#{pos_before} a #{pos_today} en {lookback_days} días"
                        ),
                        "created_at": created_at,
                    }
                )
    return alerts


def run_delta_computation(conn, settings: MonitorSettings) -> dict[str, Any]:
    snapshot_today = conn.execute(
        "SELECT MAX(snapshot_date) FROM rank_snapshots_relative"
    ).fetchone()[0]
    if not snapshot_today:
        snapshot_today = conn.execute(
            "SELECT MAX(snapshot_date) FROM rank_snapshots_absolute"
        ).fetchone()[0]
    if not snapshot_today:
        return {"alert_date": None, "alerts_created": 0, "note": "Sin snapshots en la base de datos"}

    alert_date = snapshot_today
    created_at = datetime.now(timezone.utc).isoformat()
    delete_alerts_for_date(conn, alert_date)

    all_alerts: list[dict[str, Any]] = []
    relative_summary: list[RelativeRow] = []

    for lookback in settings.lookback_days:
        relative_rows = fetch_relative_rows(conn, snapshot_today, lookback)
        relative_summary.extend(relative_rows)
        all_alerts.extend(
            build_relative_alerts(relative_rows, settings, alert_date, created_at)
        )
        all_alerts.extend(
            build_absolute_alerts(
                conn, settings, snapshot_today, lookback, alert_date, created_at
            )
        )

    for alert in all_alerts:
        insert_alert(conn, alert)
    conn.commit()

    return {
        "alert_date": alert_date,
        "alerts_created": len(all_alerts),
        "relative_rows_analyzed": len(relative_summary),
        "lookback_days": settings.lookback_days,
    }

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

from lib.config import MonitorSettings
from lib.deltas import fetch_absolute_top100


class JumpType(StrEnum):
    NEW_ENTRANT = "new_entrant"
    NEW_ENTRANT_TOP20 = "new_entrant_top20"
    NEW_ENTRANT_TOP10 = "new_entrant_top10"
    LEFT_TOP100 = "left_top100"
    SURGE_UP = "surge_up"
    SURGE_DOWN = "surge_down"
    ENTERED_TOP20 = "entered_top20"
    ENTERED_TOP10 = "entered_top10"


class JumpSeverity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"


DOMAIN_LABELS = {
    9: "Amazon.es",
    1: "Amazon.com",
    3: "Amazon.de",
}


@dataclass(frozen=True)
class CategoryJump:
    jump_type: JumpType
    severity: JumpSeverity
    domain_id: int
    category_id: str
    category_name: str
    asin: str
    rank_before: int | None
    rank_after: int | None
    positions_delta: int | None
    lookback_days: int
    snapshot_today: str
    snapshot_before: str
    message: str

    @property
    def domain_label(self) -> str:
        return DOMAIN_LABELS.get(self.domain_id, f"domain {self.domain_id}")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _subtract_days(base: str, days: int) -> str:
    return (_parse_date(base) - timedelta(days=days)).isoformat()


def _snapshot_before(conn, snapshot_today: str, lookback_days: int) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(snapshot_date) FROM rank_snapshots_absolute
        WHERE snapshot_date <= ?
        """,
        (_subtract_days(snapshot_today, lookback_days),),
    ).fetchone()[0]
    if not row or row == snapshot_today:
        return None
    return str(row)


def _severity_for_new_entrant(rank: int) -> tuple[JumpType, JumpSeverity]:
    if rank <= 10:
        return JumpType.NEW_ENTRANT_TOP10, JumpSeverity.HIGH
    if rank <= 20:
        return JumpType.NEW_ENTRANT_TOP20, JumpSeverity.HIGH
    if rank <= 50:
        return JumpType.NEW_ENTRANT, JumpSeverity.MEDIUM
    return JumpType.NEW_ENTRANT, JumpSeverity.MEDIUM


def _severity_for_move(positions_delta: int, rank_after: int) -> tuple[JumpType, JumpSeverity]:
    moved_up = positions_delta < 0
    magnitude = abs(positions_delta)

    if moved_up:
        if rank_after <= 10 or magnitude >= 50:
            return JumpType.SURGE_UP, JumpSeverity.HIGH
        return JumpType.SURGE_UP, JumpSeverity.MEDIUM
    if magnitude >= 50 or rank_after >= 80:
        return JumpType.SURGE_DOWN, JumpSeverity.HIGH
    return JumpType.SURGE_DOWN, JumpSeverity.MEDIUM


def detect_category_jumps(
    conn,
    settings: MonitorSettings,
    *,
    snapshot_today: str | None = None,
    lookback_days: int | None = None,
    domain_ids: tuple[int, ...] | None = None,
    category_ids: tuple[str, ...] | None = None,
    min_severity: JumpSeverity | None = None,
) -> list[CategoryJump]:
    if snapshot_today is None:
        snapshot_today = conn.execute(
            "SELECT MAX(snapshot_date) FROM rank_snapshots_absolute"
        ).fetchone()[0]
    if not snapshot_today:
        return []

    lookback = lookback_days or settings.lookback_days[0]
    snapshot_before = _snapshot_before(conn, snapshot_today, lookback)
    if not snapshot_before:
        return []

    query = """
        SELECT DISTINCT domain_id, category_id, category_name
        FROM rank_snapshots_absolute
        WHERE snapshot_date = ?
    """
    params: list[Any] = [snapshot_today]
    if domain_ids:
        placeholders = ",".join("?" for _ in domain_ids)
        query += f" AND domain_id IN ({placeholders})"
        params.extend(domain_ids)
    if category_ids:
        placeholders = ",".join("?" for _ in category_ids)
        query += f" AND category_id IN ({placeholders})"
        params.extend(category_ids)

    categories = conn.execute(query, params).fetchall()
    jumps: list[CategoryJump] = []

    for cat in categories:
        domain_id = int(cat["domain_id"])
        category_id = str(cat["category_id"])
        category_name = str(cat["category_name"])
        today_map = fetch_absolute_top100(conn, snapshot_today, domain_id, category_id)
        before_map = fetch_absolute_top100(conn, snapshot_before, domain_id, category_id)

        for asin in sorted(set(today_map) - set(before_map)):
            rank_after = today_map[asin]
            jump_type, severity = _severity_for_new_entrant(rank_after)
            jumps.append(
                CategoryJump(
                    jump_type=jump_type,
                    severity=severity,
                    domain_id=domain_id,
                    category_id=category_id,
                    category_name=category_name,
                    asin=asin,
                    rank_before=None,
                    rank_after=rank_after,
                    positions_delta=None,
                    lookback_days=lookback,
                    snapshot_today=snapshot_today,
                    snapshot_before=snapshot_before,
                    message=(
                        f"Nuevo en top 100 — {category_name} ({DOMAIN_LABELS.get(domain_id, domain_id)}): "
                        f"ASIN {asin} entra directamente en #{rank_after} "
                        f"(vs snapshot {snapshot_before})"
                    ),
                )
            )

        for asin in sorted(set(before_map) - set(today_map)):
            rank_before = before_map[asin]
            jumps.append(
                CategoryJump(
                    jump_type=JumpType.LEFT_TOP100,
                    severity=JumpSeverity.MEDIUM if rank_before > 50 else JumpSeverity.HIGH,
                    domain_id=domain_id,
                    category_id=category_id,
                    category_name=category_name,
                    asin=asin,
                    rank_before=rank_before,
                    rank_after=None,
                    positions_delta=None,
                    lookback_days=lookback,
                    snapshot_today=snapshot_today,
                    snapshot_before=snapshot_before,
                    message=(
                        f"Salida del top 100 — {category_name} ({DOMAIN_LABELS.get(domain_id, domain_id)}): "
                        f"ASIN {asin} (era #{rank_before} en {snapshot_before})"
                    ),
                )
            )

        threshold = settings.position_move_threshold
        for asin in sorted(set(today_map) & set(before_map)):
            rank_before = before_map[asin]
            rank_after = today_map[asin]
            move = rank_after - rank_before

            if rank_before > 20 and rank_after <= 20:
                jumps.append(
                    CategoryJump(
                        jump_type=JumpType.ENTERED_TOP20,
                        severity=JumpSeverity.HIGH,
                        domain_id=domain_id,
                        category_id=category_id,
                        category_name=category_name,
                        asin=asin,
                        rank_before=rank_before,
                        rank_after=rank_after,
                        positions_delta=move,
                        lookback_days=lookback,
                        snapshot_today=snapshot_today,
                        snapshot_before=snapshot_before,
                        message=(
                            f"Salto al top 20 — {category_name}: ASIN {asin} "
                            f"#{rank_before} → #{rank_after} ({abs(move)} posiciones)"
                        ),
                    )
                )
                continue

            if rank_before > 10 and rank_after <= 10:
                jumps.append(
                    CategoryJump(
                        jump_type=JumpType.ENTERED_TOP10,
                        severity=JumpSeverity.HIGH,
                        domain_id=domain_id,
                        category_id=category_id,
                        category_name=category_name,
                        asin=asin,
                        rank_before=rank_before,
                        rank_after=rank_after,
                        positions_delta=move,
                        lookback_days=lookback,
                        snapshot_today=snapshot_today,
                        snapshot_before=snapshot_before,
                        message=(
                            f"Salto al top 10 — {category_name}: ASIN {asin} "
                            f"#{rank_before} → #{rank_after} ({abs(move)} posiciones)"
                        ),
                    )
                )
                continue

            if abs(move) < threshold:
                continue

            jump_type, severity = _severity_for_move(move, rank_after)
            direction = "subió" if move < 0 else "bajó"
            jumps.append(
                CategoryJump(
                    jump_type=jump_type,
                    severity=severity,
                    domain_id=domain_id,
                    category_id=category_id,
                    category_name=category_name,
                    asin=asin,
                    rank_before=rank_before,
                    rank_after=rank_after,
                    positions_delta=move,
                    lookback_days=lookback,
                    snapshot_today=snapshot_today,
                    snapshot_before=snapshot_before,
                    message=(
                        f"Salto importante — {category_name}: ASIN {asin} {direction} "
                        f"#{rank_before} → #{rank_after} ({abs(move)} posiciones en {lookback}d)"
                    ),
                )
            )

    if min_severity == JumpSeverity.HIGH:
        jumps = [jump for jump in jumps if jump.severity == JumpSeverity.HIGH]

    jumps.sort(
        key=lambda jump: (
            0 if jump.severity == JumpSeverity.HIGH else 1,
            jump.rank_after if jump.rank_after is not None else 999,
        )
    )
    return jumps


def jumps_to_alert_rows(jumps: list[CategoryJump], alert_date: str, created_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for jump in jumps:
        rows.append(
            {
                "alert_date": alert_date,
                "module": "absolute",
                "alert_type": jump.jump_type.value,
                "domain_id": jump.domain_id,
                "asin": jump.asin,
                "category_id": jump.category_id,
                "rank_before": jump.rank_before,
                "rank_after": jump.rank_after,
                "delta_pct": float(jump.positions_delta) if jump.positions_delta is not None else None,
                "message": jump.message,
                "created_at": created_at,
            }
        )
    return rows


def render_jumps_text(jumps: list[CategoryJump], *, snapshot_today: str, lookback_days: int) -> str:
    lines = [
        "Saltos importantes en categorías (módulo absoluto)",
        f"Snapshot hoy: {snapshot_today} | Comparación: {lookback_days} días",
        "",
    ]
    if not jumps:
        lines.append("Sin saltos detectados (¿hay al menos 2 snapshots separados por el lookback?).")
        return "\n".join(lines)

    by_market: dict[int, list[CategoryJump]] = {}
    for jump in jumps:
        by_market.setdefault(jump.domain_id, []).append(jump)

    for domain_id in sorted(by_market):
        label = DOMAIN_LABELS.get(domain_id, f"domain {domain_id}")
        lines.append(f"## {label}")
        for jump in by_market[domain_id]:
            prefix = "🔴" if jump.severity == JumpSeverity.HIGH else "🟡"
            lines.append(f"{prefix} [{jump.jump_type.value}] {jump.message}")
        lines.append("")

    return "\n".join(lines).strip()

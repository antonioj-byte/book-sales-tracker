from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from lib.config import REPORTS_DIR, get_monitor_settings  # noqa: E402
from lib.db import connect, init_schema, insert_alert  # noqa: E402
from lib.jumps import (  # noqa: E402
    JumpSeverity,
    detect_category_jumps,
    jumps_to_alert_rows,
    render_jumps_text,
)


def _parse_markets(raw: str | None) -> tuple[int, ...] | None:
    if not raw:
        return None
    return tuple(int(part.strip()) for part in raw.split(",") if part.strip())


def _parse_categories(raw: str | None) -> tuple[str, ...] | None:
    if not raw:
        return None
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detecta saltos importantes en rankings absolutos por categoría (offline, SQLite)"
    )
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Días hacia atrás para comparar (default: primer valor de LOOKBACK_DAYS)",
    )
    parser.add_argument(
        "--markets",
        type=str,
        default=None,
        help="Mercados Keepa a incluir, ej. 9,1 (Amazon.es + Amazon.com)",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default=None,
        help="IDs de categoría Keepa separados por coma (opcional)",
    )
    parser.add_argument(
        "--min-severity",
        choices=["high", "medium", "all"],
        default="all",
        help="Filtrar por severidad (default: all)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--write-alerts",
        action="store_true",
        help="Persistir saltos en la tabla alerts (sobrescribe alertas absolute del día)",
    )
    args = parser.parse_args()

    settings = get_monitor_settings(db_path=args.db_path)
    conn = connect(settings.db_path)
    init_schema(conn)

    min_severity = None if args.min_severity == "all" else JumpSeverity(args.min_severity)
    jumps = detect_category_jumps(
        conn,
        settings,
        lookback_days=args.lookback_days,
        domain_ids=_parse_markets(args.markets),
        category_ids=_parse_categories(args.categories),
        min_severity=min_severity,
    )

    snapshot_today = conn.execute(
        "SELECT MAX(snapshot_date) FROM rank_snapshots_absolute"
    ).fetchone()[0]
    lookback = args.lookback_days or settings.lookback_days[0]

    if args.write_alerts and snapshot_today and jumps:
        created_at = datetime.now(timezone.utc).isoformat()
        for row in jumps_to_alert_rows(jumps, snapshot_today, created_at):
            insert_alert(conn, row)
        conn.commit()
        print(f"Alertas añadidas: {len(jumps)} (fecha {snapshot_today})")

    if args.format == "json":
        payload = [
            {
                "jump_type": jump.jump_type.value,
                "severity": jump.severity.value,
                "domain_id": jump.domain_id,
                "domain_label": jump.domain_label,
                "category_id": jump.category_id,
                "category_name": jump.category_name,
                "asin": jump.asin,
                "rank_before": jump.rank_before,
                "rank_after": jump.rank_after,
                "positions_delta": jump.positions_delta,
                "lookback_days": jump.lookback_days,
                "message": jump.message,
            }
            for jump in jumps
        ]
        content = json.dumps(payload, ensure_ascii=False, indent=2)
    elif args.format == "markdown":
        content = render_jumps_text(jumps, snapshot_today=snapshot_today or "—", lookback_days=lookback)
        content = content.replace("🔴", "**").replace("🟡", "*")
    else:
        content = render_jumps_text(jumps, snapshot_today=snapshot_today or "—", lookback_days=lookback)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Informe guardado: {args.output}")
    else:
        print(content)

    print(f"\nResumen: {len(jumps)} salto(s) detectado(s)")
    conn.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from lib.config import REPORTS_DIR, get_monitor_settings  # noqa: E402
from lib.db import connect, init_schema  # noqa: E402
from lib.deltas import fetch_relative_rows  # noqa: E402


DOMAIN_LABELS = {
    9: "Amazon.es",
    1: "Amazon.com",
    3: "Amazon.de",
}


def _domain_label(domain_id: int | None) -> str:
    if domain_id is None:
        return "—"
    return DOMAIN_LABELS.get(domain_id, f"domain {domain_id}")


def fetch_alerts(conn, since_date: str) -> list:
    return conn.execute(
        """
        SELECT * FROM alerts
        WHERE alert_date >= ?
        ORDER BY alert_date DESC, module, alert_type, id
        """,
        (since_date,),
    ).fetchall()


def fetch_category_context(conn, category_id: str, domain_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT name, product_count FROM category_tree
        WHERE category_id = ? AND domain_id = ?
        """,
        (category_id, domain_id),
    ).fetchone()
    return dict(row) if row else None


def build_relative_comparison(conn, snapshot_today: str, lookback_days: int) -> list[str]:
    rows = fetch_relative_rows(conn, snapshot_today, lookback_days)
    if not rows:
        return [f"No hay datos comparables a {lookback_days} días."]

    propios = [row for row in rows if row.tipo == "propio"]
    escauteados = [row for row in rows if row.tipo == "escauteado"]
    lines = [f"Comparativa editorial ({lookback_days} días):"]

    for row in propios:
        delta_txt = f"{row.delta_pct:+.1f}%" if row.delta_pct is not None else "sin delta"
        lines.append(
            f"  PROPIO — {row.nombre_libro}: rank {row.rank_before} → {row.rank_today} ({delta_txt})"
        )
    for row in escauteados:
        delta_txt = f"{row.delta_pct:+.1f}%" if row.delta_pct is not None else "sin delta"
        lines.append(
            f"  ESCAUTEADO — {row.nombre_libro}: rank {row.rank_before} → {row.rank_today} ({delta_txt})"
        )

    if propios and escauteados and propios[0].delta_pct is not None and escauteados[0].delta_pct is not None:
        better = "propio" if propios[0].delta_pct < escauteados[0].delta_pct else "escauteado"
        lines.append(
            f"  → Mejor evolución relativa ({lookback_days}d): {better}"
        )
    return lines


def render_markdown(conn, settings, since_date: str) -> str:
    snapshot_today = conn.execute(
        "SELECT MAX(snapshot_date) FROM rank_snapshots_relative"
    ).fetchone()[0] or conn.execute(
        "SELECT MAX(snapshot_date) FROM rank_snapshots_absolute"
    ).fetchone()[0]

    lines = [
        "# Informe Keepa Monitor",
        "",
        f"Periodo de alertas: últimos {settings.report_days} días (desde {since_date})",
        "",
    ]

    lines.append("## Módulo relativo")
    lines.append("")
    for lookback in settings.lookback_days:
        lines.extend(build_relative_comparison(conn, snapshot_today, lookback))
        lines.append("")

    alerts = fetch_alerts(conn, since_date)
    relative_alerts = [a for a in alerts if a["module"] == "relative"]
    absolute_alerts = [a for a in alerts if a["module"] == "absolute"]

    if relative_alerts:
        lines.append("### Alertas relativas")
        for alert in relative_alerts:
            lines.append(f"- {alert['message']}")
        lines.append("")

    lines.append("## Módulo absoluto")
    lines.append("")
    if not absolute_alerts:
        lines.append("_Sin alertas absolutas en el periodo._")
    else:
        by_category: dict[str, list] = {}
        for alert in absolute_alerts:
            key = f"{alert['category_id']}@{alert['domain_id']}"
            by_category.setdefault(key, []).append(alert)

        for key, cat_alerts in by_category.items():
            category_id, domain_id = key.split("@")
            ctx = fetch_category_context(conn, category_id, int(domain_id))
            cat_name = cat_alerts[0]["message"].split(" en ")[1].split(" (")[0] if cat_alerts else category_id
            product_count = ctx["product_count"] if ctx and ctx.get("product_count") else "desconocido"
            lines.append(
                f"### {cat_name} — {_domain_label(int(domain_id))}"
            )
            lines.append(f"Contexto: categoría con ~{product_count} productos en Keepa.")
            entered = [a for a in cat_alerts if a["alert_type"] == "entered_top100"]
            left = [a for a in cat_alerts if a["alert_type"] == "left_top100"]
            moved = [a for a in cat_alerts if a["alert_type"] == "position_move"]
            if entered:
                lines.append(f"- **Entraron al top 100 ({len(entered)}):**")
                for a in entered[:10]:
                    lines.append(f"  - {a['asin']} (#{a['rank_after']})")
            if left:
                lines.append(f"- **Salieron del top 100 ({len(left)}):**")
                for a in left[:10]:
                    lines.append(f"  - {a['asin']} (era #{a['rank_before']})")
            if moved:
                lines.append(f"- **Movimientos grandes ({len(moved)}):**")
                for a in moved[:10]:
                    lines.append(f"  - {a['message']}")
            lines.append("")

    return "\n".join(lines)


def export_csv(alerts, output_path: Path) -> None:
    if not alerts:
        output_path.write_text("", encoding="utf-8")
        return
    fieldnames = alerts[0].keys()
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for alert in alerts:
            writer.writerow(dict(alert))


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera informe legible desde alertas SQLite")
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--days", type=int, default=None, help="Días hacia atrás (default REPORT_DAYS)")
    parser.add_argument(
        "--format",
        choices=["markdown", "text", "csv"],
        default="markdown",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    settings = get_monitor_settings(db_path=args.db_path)
    report_days = args.days or settings.report_days
    since_date = (date.today() - timedelta(days=report_days)).isoformat()

    conn = connect(settings.db_path)
    init_schema(conn)
    alerts = fetch_alerts(conn, since_date)

    if args.format == "csv":
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output = args.output or REPORTS_DIR / f"report_{date.today().isoformat()}.csv"
        export_csv(alerts, output)
        print(f"CSV exportado: {output}")
    else:
        content = render_markdown(conn, settings, since_date)
        if args.format == "text":
            for prefix in ("### ", "## ", "# "):
                content = content.replace(prefix, "")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(f"Informe guardado: {args.output}")
        else:
            print(content)

    conn.close()


if __name__ == "__main__":
    main()

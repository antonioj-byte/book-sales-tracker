from __future__ import annotations

import streamlit as st

from book_sales_tracker.monitor_reader import (
    DEFAULT_MONITOR_DB,
    db_exists,
    detect_jumps_for_ui,
    domain_label,
    fetch_market_indices,
    fetch_relative_history,
    fetch_turnover_series,
    list_markets_with_data,
    connect,
    latest_snapshot_dates,
    relative_comparison_summary,
    short_market_label,
)
from book_sales_tracker.ui.components import (
    axis_label,
    empty_state,
    error_banner,
    index_row,
    kpi_strip,
    movement_row,
    page_header,
    section_header,
)
from book_sales_tracker.visualization import build_market_turnover_chart


MARKET_ORDER = ["Global", "España", "UK", "Francia", "EE.UU.", "Italia", "Alemania"]
TIMEFRAMES = {"1d": 1, "1s": 7, "1m": 30, "6m": 180, "1a": 365}


def _market_pill_options(markets: list[tuple[int, str]]) -> tuple[list[str], dict[str, int | None]]:
    labels = ["Global"]
    mapping: dict[str, int | None] = {"Global": None}
    for domain_id, _ in markets:
        short = short_market_label(domain_id)
        if short not in mapping:
            labels.append(short)
            mapping[short] = domain_id
    labels.sort(key=lambda item: MARKET_ORDER.index(item) if item in MARKET_ORDER else 99)
    return labels, mapping


def _kpi_accent(axis: str, index: int) -> str:
    if axis == "F":
        return "purple"
    if axis == "NF":
        return "cyan"
    return ["purple", "cyan", "amber"][index % 3]


def _format_turnover_change(turnover: float | None) -> tuple[str, str]:
    if turnover is None:
        return "—", "neutral"
    if turnover >= 20:
        return f"▲ {turnover}% rotación", "positive"
    if turnover >= 8:
        return f"▲ {turnover}% rotación", "neutral"
    return f"→ {turnover}% rotación", "neutral"


def render_monitor_tab() -> None:
    page_header("Mercados", subtitle="Terminal editorial · rankings Amazon")

    if not db_exists():
        empty_state(
            "Sin datos de mercado",
            "Ejecuta keepa-monitor/scripts/setup_db.py y daily_fetch.py "
            "para empezar a acumular índices.",
        )
        st.code("cd keepa-monitor\npython3 scripts/setup_db.py\npython3 scripts/daily_fetch.py")
        return

    try:
        conn = connect()
    except FileNotFoundError as exc:
        error_banner(str(exc))
        return

    try:
        dates = latest_snapshot_dates(conn)
        markets = list_markets_with_data(conn)
        absolute_markets = [
            (domain_id, label)
            for domain_id, label in markets
            if conn.execute(
                "SELECT 1 FROM rank_snapshots_absolute WHERE domain_id = ? LIMIT 1",
                (domain_id,),
            ).fetchone()
        ]

        if not absolute_markets:
            empty_state(
                "Mercados sin índices",
                "Ejecuta daily_fetch.py para cargar tops por categoría.",
            )
            return

        pill_labels, pill_map = _market_pill_options(absolute_markets)
        col_m1, col_m2 = st.columns([3, 2])
        with col_m1:
            selected_market = st.radio(
                "Mercado",
                options=pill_labels,
                horizontal=True,
                label_visibility="collapsed",
                key="rv_market_filter",
            )
        with col_m2:
            tf_label = st.radio(
                "Ventana",
                options=list(TIMEFRAMES.keys()),
                index=2,
                horizontal=True,
                label_visibility="collapsed",
                key="rv_timeframe_filter",
            )

        lookback = TIMEFRAMES[tf_label]
        st.caption(f"Último snapshot · {dates['absolute'] or '—'}")

        domain_filter = pill_map[selected_market]
        market_domains = (
            [domain_id for domain_id, _ in absolute_markets]
            if domain_filter is None
            else [domain_filter]
        )

        all_indices: list[dict] = []
        for domain_id in market_domains:
            all_indices.extend(
                fetch_market_indices(conn, domain_id=domain_id, lookback_days=lookback)
            )

        fiction = [item for item in all_indices if item["axis"] == "F"]
        nonfiction = [item for item in all_indices if item["axis"] == "NF"]

        kpi_items = []
        for bucket, default_label in ((fiction, "Ficción"), (nonfiction, "No ficción")):
            if not bucket:
                kpi_items.append(
                    {
                        "label": default_label,
                        "change_text": "—",
                        "change_class": "neutral",
                        "accent": "purple" if default_label == "Ficción" else "cyan",
                    }
                )
                continue
            avg_turnover = round(
                sum(item["turnover_pct"] or 0 for item in bucket) / len(bucket), 1
            )
            change_text, change_class = _format_turnover_change(avg_turnover)
            kpi_items.append(
                {
                    "label": default_label,
                    "change_text": change_text,
                    "change_class": change_class,
                    "accent": "purple" if default_label == "Ficción" else "cyan",
                }
            )

        if market_domains:
            kpi_items.append(
                {
                    "label": selected_market if selected_market != "Global" else "Mercados",
                    "change_text": f"{len(all_indices)} índices",
                    "change_class": "neutral",
                    "accent": "amber",
                }
            )

        kpi_strip(kpi_items[:3])

        chart_domain = market_domains[0]
        chart_categories = [item["category_id"] for item in all_indices[:3]]
        turnover_df = fetch_turnover_series(
            conn,
            domain_id=chart_domain,
            category_ids=chart_categories,
        )
        chart = build_market_turnover_chart(turnover_df)
        if chart:
            st.plotly_chart(chart, use_container_width=True)
        else:
            empty_state(
                "Histórico en construcción",
                "Necesitas al menos 2 snapshots diarios para ver la evolución de rotación.",
            )

        section_header("Índices", link_text="Ver todo")

        if fiction:
            axis_label("Ficción")
            for index, item in enumerate(fiction):
                index_row(
                    icon=item["market"][:2].upper(),
                    badge="F",
                    title=item["category_name"],
                    subtitle=f"Top 100 · {item['market']}",
                    value=f"#{item['avg_top10']:.0f}" if item["avg_top10"] else "—",
                    delta=item["delta_text"],
                    delta_class=item["delta_class"],
                )

        if nonfiction:
            axis_label("No ficción")
            for index, item in enumerate(nonfiction):
                index_row(
                    icon=item["market"][:2].upper(),
                    badge="NF",
                    title=item["category_name"],
                    subtitle=f"Top 100 · {item['market']}",
                    value=f"#{item['avg_top10']:.0f}" if item["avg_top10"] else "—",
                    delta=item["delta_text"],
                    delta_class=item["delta_class"],
                )

        section_header("Movimientos")
        try:
            jumps = detect_jumps_for_ui(
                conn,
                domain_ids=tuple(market_domains),
                lookback_days=lookback,
                min_severity="high",
            )
        except Exception as exc:
            error_banner(f"No se pudieron calcular movimientos: {exc}")
            jumps = []

        if not jumps:
            empty_state(
                "Sin movimientos bruscos",
                f"No hay entradas ni saltos relevantes en los últimos {lookback} días.",
            )
        else:
            for jump in jumps[:12]:
                friendly = jump.message.replace("new_entrant", "Nueva entrada").replace(
                    "top10", "top 10"
                )
                movement_row(friendly, severity=jump.severity.value)

        section_header("Mi watchlist")
        relative = fetch_relative_history(conn)
        if not relative:
            empty_state(
                "Watchlist vacía",
                "Añade ASINs propios y escauteados en keepa-monitor/config/tracked_asins.csv",
            )
        else:
            summary = relative_comparison_summary(relative)
            if summary.empty:
                empty_state("Sin histórico", "Aún no hay snapshots relativos acumulados.")
            else:
                for _, row in summary.head(8).iterrows():
                    rank = row["rank_último"]
                    delta = row["delta_%"]
                    if delta is None:
                        delta_text = "—"
                        delta_class = "neutral"
                    elif delta < 0:
                        delta_text = f"▲ {abs(delta):.1f}%"
                        delta_class = "positive"
                    elif delta > 0:
                        delta_text = f"▼ {delta:.1f}%"
                        delta_class = "negative"
                    else:
                        delta_text = "→ 0%"
                        delta_class = "neutral"
                    badge = "P" if row["tipo"] == "propio" else "E"
                    index_row(
                        icon=badge,
                        badge=row["mercado"][:2],
                        title=str(row["libro"])[:48],
                        subtitle=f"{row['tipo'].title()} · {row['mercado']}",
                        value=f"#{int(rank)}" if rank else "—",
                        delta=delta_text,
                        delta_class=delta_class,
                    )
    finally:
        conn.close()

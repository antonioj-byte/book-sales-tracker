from __future__ import annotations

import streamlit as st

from book_sales_tracker.monitor_reader import (
    DEFAULT_MONITOR_DB,
    absolute_to_dataframe,
    db_exists,
    detect_jumps_for_ui,
    domain_label,
    fetch_absolute_top,
    list_categories,
    list_markets_with_data,
    connect,
    latest_snapshot_dates,
)


def render_monitor_tab() -> None:
    st.subheader("Monitor editorial")
    st.caption(
        "Movimientos bruscos en listas de categorías por mercado (top 100 Keepa). "
        "Datos del fetch diario — sin comparativa de títulos propios."
    )

    if not db_exists():
        st.warning(
            f"No hay base de datos del monitor en `{DEFAULT_MONITOR_DB}`. "
            "Ejecuta primero:\n\n"
            "```bash\ncd keepa-monitor\npython scripts/setup_db.py\npython scripts/daily_fetch.py\n```"
        )
        return

    try:
        conn = connect()
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    try:
        dates = latest_snapshot_dates(conn)
        st.metric("Último snapshot absoluto", dates["absolute"] or "—")

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
            st.info("Sin rankings absolutos por categoría. Ejecuta `daily_fetch.py`.")
            return

        market_options = {label: domain_id for domain_id, label in absolute_markets}
        selected_labels = st.multiselect(
            "Mercados",
            options=list(market_options.keys()),
            default=list(market_options.keys())[:2]
            if len(market_options) >= 2
            else list(market_options.keys()),
        )
        selected_domains = tuple(market_options[label] for label in selected_labels)
        lookback = st.slider("Ventana comparación (días)", min_value=1, max_value=30, value=7)
        min_severity = st.selectbox(
            "Severidad mínima",
            options=["high", "all"],
            format_func=lambda x: "Alta (saltos bruscos)" if x == "high" else "Todas",
        )

        st.markdown("---")
        st.markdown("#### Saltos y movimientos bruscos")

        try:
            jumps = detect_jumps_for_ui(
                conn,
                domain_ids=selected_domains,
                lookback_days=lookback,
                min_severity=min_severity,
            )
        except Exception as exc:
            st.error(f"No se pudieron calcular saltos: {exc}")
            jumps = []

        if not jumps:
            st.caption(
                "Sin saltos en el periodo. Necesitas al menos **2 snapshots** diarios "
                f"separados ~{lookback} días (`daily_fetch.py` en cron)."
            )
        else:
            by_market: dict[int, list] = {}
            for jump in jumps:
                by_market.setdefault(jump.domain_id, []).append(jump)
            for domain_id in sorted(by_market):
                st.markdown(f"**{domain_label(domain_id)}** — {len(by_market[domain_id])} evento(s)")
                for jump in by_market[domain_id][:20]:
                    icon = "🔴" if jump.severity.value == "high" else "🟡"
                    st.markdown(f"{icon} {jump.message}")
                if len(by_market[domain_id]) > 20:
                    st.caption(f"… {len(by_market[domain_id]) - 20} más")

        st.markdown("---")
        st.markdown("#### Top categorías (referencia)")

        for domain_id in selected_domains:
            label = domain_label(domain_id)
            categories = list_categories(conn, domain_id=domain_id)
            if not categories:
                continue

            cat_labels = {f"{c['category_name']}": c for c in categories}
            chosen = st.selectbox(
                f"Categoría — {label}",
                options=list(cat_labels.keys()),
                key=f"monitor_cat_{domain_id}",
            )
            cat = cat_labels[chosen]
            top_rows = fetch_absolute_top(
                conn,
                domain_id=cat["domain_id"],
                category_id=cat["category_id"],
                limit=100,
            )
            top_df = absolute_to_dataframe(top_rows)
            if top_df.empty:
                continue
            st.caption(f"Snapshot {top_rows[0].snapshot_date}")
            st.dataframe(top_df.head(15), use_container_width=True, hide_index=True)
    finally:
        conn.close()

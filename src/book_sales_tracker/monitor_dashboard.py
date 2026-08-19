from __future__ import annotations

import plotly.express as px
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
    fetch_relative_history,
    latest_snapshot_dates,
    relative_comparison_summary,
    relative_to_dataframe,
)


def render_monitor_tab() -> None:
    st.subheader("Monitor editorial")
    st.caption(
        "Datos del fetch diario (`keepa-monitor/`): tus títulos vs escauteados "
        "y rankings absolutos por categoría en distintos mercados."
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

    dates = latest_snapshot_dates(conn)
    col_a, col_b = st.columns(2)
    col_a.metric("Último snapshot (relativo)", dates["relative"] or "—")
    col_b.metric("Último snapshot (absoluto)", dates["absolute"] or "—")

    tab_own, tab_markets = st.tabs(["Mis títulos", "Mercados y categorías"])

    with tab_own:
        _render_own_titles(conn, dates)

    with tab_markets:
        _render_markets(conn)

    conn.close()


def _render_own_titles(conn, dates: dict) -> None:
    snapshots = fetch_relative_history(conn)
    if not snapshots:
        st.info(
            "Sin datos relativos todavía. Configura `keepa-monitor/config/tracked_asins.csv` "
            "y ejecuta `daily_fetch.py`."
        )
        return

    df = relative_to_dataframe(snapshots)
    summary = relative_comparison_summary(snapshots)

    st.markdown("#### Comparativa propio vs escauteado")
    if len(summary) > 0:
        st.dataframe(
            summary,
            use_container_width=True,
            hide_index=True,
            column_config={
                "rank_inicio": st.column_config.NumberColumn(format="%d"),
                "rank_último": st.column_config.NumberColumn(format="%d"),
                "delta_%": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
    else:
        st.caption("Sin resumen comparativo.")

    unique_dates = sorted(df["fecha"].unique())
    if len(unique_dates) >= 2:
        st.markdown("#### Evolución del sales rank")
        fig = px.line(
            df.dropna(subset=["sales_rank"]),
            x="fecha",
            y="sales_rank",
            color="libro",
            line_dash="tipo",
            markers=True,
            labels={"fecha": "Fecha", "sales_rank": "Sales rank", "libro": "Libro"},
            title="BSR diario — propio vs escauteado",
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption(
            "Con un solo día de datos no hay curva de evolución. "
            "Tras varios `daily_fetch` verás la gráfica."
        )

    st.markdown("#### Histórico detallado")
    market_filter = st.selectbox(
        "Mercado (relativo)",
        options=sorted(df["mercado"].unique()),
        key="relative_market_filter",
    )
    filtered = df[df["mercado"] == market_filter]
    st.dataframe(filtered, use_container_width=True, hide_index=True)


def _render_markets(conn) -> None:
    markets = list_markets_with_data(conn)
    if not markets:
        st.info("Sin datos absolutos por mercado.")
        return

    market_options = {label: domain_id for domain_id, label in markets}
    selected_labels = st.multiselect(
        "Mercados",
        options=list(market_options.keys()),
        default=list(market_options.keys())[:2] if len(market_options) >= 2 else list(market_options.keys()),
    )
    selected_domains = tuple(market_options[label] for label in selected_labels)

    lookback = st.slider("Lookback saltos (días)", min_value=1, max_value=30, value=7)

    for domain_id in selected_domains:
        label = domain_label(domain_id)
        st.markdown(f"### {label}")

        categories = list_categories(conn, domain_id=domain_id)
        if not categories:
            st.caption("Sin categorías para este mercado.")
            continue

        cat_labels = {
            f"{cat['category_name']} ({cat['category_id']})": cat for cat in categories
        }
        chosen = st.selectbox(
            f"Categoría — {label}",
            options=list(cat_labels.keys()),
            key=f"cat_{domain_id}",
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
            st.caption("Sin ranking para esta categoría.")
            continue

        st.markdown(f"**Top 100** — snapshot {top_rows[0].snapshot_date}")
        show_n = st.slider(
            "Filas a mostrar",
            min_value=10,
            max_value=100,
            value=20,
            key=f"topn_{domain_id}_{cat['category_id']}",
        )
        st.dataframe(top_df.head(show_n), use_container_width=True, hide_index=True)

    if selected_domains:
        st.markdown("#### Saltos importantes")
        try:
            jumps = detect_jumps_for_ui(
                conn,
                domain_ids=selected_domains,
                lookback_days=lookback,
                min_severity="high",
            )
        except Exception as exc:
            st.error(f"No se pudieron calcular saltos: {exc}")
            jumps = []

        if not jumps:
            st.caption(
                "Sin saltos de alta severidad en el periodo (¿hay al menos 2 snapshots separados por el lookback?)."
            )
        else:
            for jump in jumps[:25]:
                st.markdown(f"- **{jump.domain_label}** — {jump.message}")
            if len(jumps) > 25:
                st.caption(f"… y {len(jumps) - 25} más. Usa `detect_jumps.py` para el listado completo.")

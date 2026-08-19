from __future__ import annotations

import plotly.express as px
import streamlit as st

from book_sales_tracker.marketplace import list_marketplace_options
from book_sales_tracker.models import PipelineResult
from book_sales_tracker.pipeline import PipelineError, run_pipeline


def _parse_isbn_list(raw: str) -> list[str]:
    parts: list[str] = []
    for line in raw.replace(",", "\n").splitlines():
        token = line.strip()
        if token:
            parts.append(token)
    seen: set[str] = set()
    unique: list[str] = []
    for isbn in parts:
        key = isbn.replace("-", "")
        if key not in seen:
            seen.add(key)
            unique.append(isbn)
    return unique


def _comparison_summary(results: list[PipelineResult]) -> list[dict]:
    rows: list[dict] = []
    for result in results:
        summary = result.summary
        rows.append(
            {
                "libro": result.book.title,
                "isbn": result.book.isbn_13 or result.book.isbn_10 or "—",
                "asin": result.keepa.asin,
                "bsr_mín": summary.min_bsr,
                "bsr_máx": summary.max_bsr,
                "mejor_tramo": summary.best_tier.label_es if summary.best_tier else "—",
                "tramo_inicio": summary.start_tier.label_es if summary.start_tier else "—",
                "tramo_fin": summary.end_tier.label_es if summary.end_tier else "—",
                "cambios_tramo": summary.tier_changes,
                "días_datos": summary.total_days,
            }
        )
    return rows


def _build_comparison_bsr_chart(results: list[PipelineResult]):
    records: list[dict] = []
    for result in results:
        label = result.book.title
        if len(label) > 40:
            label = label[:37] + "…"
        for point in result.bsr_series:
            records.append(
                {
                    "fecha": point.timestamp.date(),
                    "bsr": point.bsr,
                    "libro": label,
                }
            )
    if not records:
        return None
    import pandas as pd

    df = pd.DataFrame(records)
    fig = px.line(
        df,
        x="fecha",
        y="bsr",
        color="libro",
        markers=True,
        labels={"fecha": "Fecha", "bsr": "Sales rank", "libro": "Libro"},
        title="Comparativa BSR",
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def render_comparator_tab(settings) -> None:
    st.subheader("Comparador ISBN")
    st.caption(
        "Compara la performance de dos o más libros en el mismo marketplace y periodo. "
        "Solo BSR y tramos — sin estimación IA (ahorra tokens Gemini)."
    )

    marketplace_options = list_marketplace_options()
    marketplace_labels = {label: code for code, label in marketplace_options}
    default_label = next(
        (label for code, label in marketplace_options if code == settings.default_amazon_domain),
        marketplace_options[0][1],
    )

    from datetime import date, timedelta

    today = date.today()
    default_start = today - timedelta(days=90)

    with st.form("comparator_form"):
        isbns_raw = st.text_area(
            "ISBNs (uno por línea o separados por coma)",
            placeholder="9788410178595\n9788433964380",
            height=100,
        )
        marketplace_label = st.selectbox(
            "Marketplace Amazon",
            options=list(marketplace_labels.keys()),
            index=list(marketplace_labels.keys()).index(default_label),
        )
        date_cols = st.columns(2)
        start_date = date_cols[0].date_input("Fecha inicio", value=default_start)
        end_date = date_cols[1].date_input("Fecha fin", value=today)
        submitted = st.form_submit_button("Comparar", type="primary")

    if not submitted:
        return

    isbns = _parse_isbn_list(isbns_raw)
    if len(isbns) < 2:
        st.error("Introduce al menos **2 ISBNs** distintos.")
        return
    if len(isbns) > 6:
        st.warning("Máximo recomendado: 6 ISBNs por comparación (coste Keepa: 1 token/ISBN).")

    marketplace_code = marketplace_labels[marketplace_label]
    results: list[PipelineResult] = []
    errors: list[str] = []

    progress = st.progress(0, text="Consultando Keepa…")
    for index, isbn in enumerate(isbns):
        progress.progress((index + 1) / len(isbns), text=f"Consultando {isbn}…")
        try:
            result = run_pipeline(
                settings,
                isbn=isbn,
                book=None,
                marketplace_code=marketplace_code,
                start_date=start_date,
                end_date=end_date,
                include_estimate=False,
            )
            results.append(result)
        except PipelineError as exc:
            errors.append(f"{isbn}: {exc}")

    progress.empty()

    for message in errors:
        st.error(message)

    if len(results) < 2:
        st.error("Se necesitan al menos 2 libros con datos válidos para comparar.")
        return

    st.success(f"Comparación lista — {len(results)} libros.")

    summary_rows = _comparison_summary(results)
    st.markdown("#### Resumen comparativo")
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    fig = _build_comparison_bsr_chart(results)
    if fig:
        st.markdown("#### Evolución BSR superpuesta")
        st.plotly_chart(fig, use_container_width=True)

    best = min(summary_rows, key=lambda row: row["bsr_mín"] or float("inf"))
    if best["bsr_mín"]:
        st.info(
            f"**Mejor BSR mínimo** en el periodo: {best['libro']} (rank {best['bsr_mín']:,})."
        )

    with st.expander("Detalle por libro"):
        for result in results:
            st.markdown(f"**{result.book.title}** — ASIN `{result.keepa.asin}`")
            st.caption(
                f"Tramos: {result.summary.start_tier.label_es if result.summary.start_tier else '—'} "
                f"→ {result.summary.end_tier.label_es if result.summary.end_tier else '—'} | "
                f"Cambios: {result.summary.tier_changes}"
            )

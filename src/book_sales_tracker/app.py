from datetime import date, timedelta

import streamlit as st

from book_sales_tracker.config import get_settings
from book_sales_tracker.google_books import BookNotFoundError
from book_sales_tracker.marketplace import list_marketplace_options
from book_sales_tracker.models import BookMetadata, BookSearchResult
from book_sales_tracker.isbn_comparator import render_comparator_tab
from book_sales_tracker.monitor_dashboard import render_monitor_tab
from book_sales_tracker.publisher_catalog import render_publisher_catalog_tab
from book_sales_tracker.pipeline import PipelineError, resolve_book_by_title, run_pipeline
from book_sales_tracker.visualization import (
    build_tier_distribution_chart,
    build_tier_timeline_chart,
    points_to_dataframe,
)


def _render_book_header(result) -> None:
    book = result.book
    col1, col2 = st.columns([1, 3])
    with col1:
        if book.thumbnail_url:
            st.image(book.thumbnail_url, width=140)
    with col2:
        st.title(book.title)
        if book.authors:
            st.write("**Autor(es):**", ", ".join(book.authors))
        if book.publisher:
            st.write("**Editorial:**", book.publisher)
        if book.published_date:
            st.write("**Fecha de publicación:**", book.published_date)
        if book.categories:
            st.write("**Categoría(s):**", ", ".join(book.categories))

    meta_cols = st.columns(4)
    meta_cols[0].metric("ISBN-13", book.isbn_13 or "—")
    meta_cols[1].metric("ISBN-10", book.isbn_10 or "—")
    meta_cols[2].metric("ASIN", result.keepa.asin)
    meta_cols[3].metric("Marketplace", result.marketplace_label)


def _render_summary_metrics(result) -> None:
    summary = result.summary
    cols = st.columns(4)
    cols[0].metric("BSR mínimo", summary.min_bsr or "—")
    cols[1].metric("BSR máximo", summary.max_bsr or "—")
    cols[2].metric("Mejor tramo", summary.best_tier.label_es if summary.best_tier else "—")
    cols[3].metric("Cambios de tramo", summary.tier_changes)


def _render_estimate(result) -> None:
    estimate = result.estimate
    st.subheader("Estimación de ventas (IA)")
    st.info(
        "Esta estimación se basa en el BSR, un ranking relativo. "
        "No es una cifra oficial de ventas de Amazon."
    )
    st.markdown(f"**Rango estimado:** {estimate.range_text}")
    st.markdown(f"**Nivel de confianza:** {estimate.confidence}")
    st.markdown(f"**Explicación:** {estimate.explanation}")


def _run_analysis(
    settings,
    *,
    isbn: str | None,
    book: BookMetadata | None,
    marketplace_code: str,
    start_date: date,
    end_date: date,
) -> None:
    with st.spinner("Consultando metadatos, Keepa y generando estimación..."):
        try:
            result = run_pipeline(
                settings,
                isbn=isbn,
                book=book,
                marketplace_code=marketplace_code,
                start_date=start_date,
                end_date=end_date,
            )
        except PipelineError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"Error inesperado: {exc}")
            return

    st.success("Análisis completado.")

    keepa = result.keepa
    if keepa.bsr_available_from and keepa.bsr_available_to:
        avail_from = keepa.bsr_available_from.date().isoformat()
        avail_to = keepa.bsr_available_to.date().isoformat()
        req_from = result.date_range_start.isoformat()
        req_to = result.date_range_end.isoformat()
        if result.date_range_start < keepa.bsr_available_from.date():
            st.warning(
                f"Pediste datos desde **{req_from}**, pero Keepa solo tiene histórico BSR "
                f"en {result.marketplace_label} desde **{avail_from}** hasta **{avail_to}**. "
                "El gráfico muestra la intersección entre tu rango y los datos disponibles."
            )
        elif req_from != result.bsr_series[0].timestamp.date().isoformat():
            st.info(
                f"Histórico BSR disponible en Keepa: **{avail_from}** → **{avail_to}** "
                f"(periodo analizado: {req_from} → {req_to})."
            )

    _render_book_header(result)
    st.divider()
    _render_summary_metrics(result)

    st.subheader("Evolución del tramo BSR")
    st.plotly_chart(build_tier_timeline_chart(result.bsr_series), use_container_width=True)

    chart_cols = st.columns(2)
    with chart_cols[0]:
        st.plotly_chart(
            build_tier_distribution_chart(result.summary),
            use_container_width=True,
        )
    with chart_cols[1]:
        st.subheader("Tabla diaria")
        st.dataframe(
            points_to_dataframe(result.bsr_series),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    _render_estimate(result)


def _render_analysis_tab(settings) -> None:
    st.subheader("Análisis ISBN")
    st.caption("Evolución de un solo libro: BSR, tramos, estimación IA (Keepa + Gemini).")

    marketplace_options = list_marketplace_options()
    marketplace_labels = {label: code for code, label in marketplace_options}
    default_marketplace = settings.default_amazon_domain
    default_label = next(
        (label for code, label in marketplace_options if code == default_marketplace),
        marketplace_options[0][1],
    )

    today = date.today()
    default_start = today - timedelta(days=90)

    with st.form("analysis_form"):
        search_mode = st.radio(
            "Buscar por",
            options=["ISBN", "Título"],
            horizontal=True,
        )
        query = st.text_input(
            "ISBN o título del libro",
            placeholder="9788410178595 o nombre del libro",
        )
        marketplace_label = st.selectbox(
            "Marketplace Amazon",
            options=list(marketplace_labels.keys()),
            index=list(marketplace_labels.keys()).index(default_label),
        )
        date_cols = st.columns(2)
        start_date = date_cols[0].date_input("Fecha inicio", value=default_start)
        end_date = date_cols[1].date_input("Fecha fin", value=today)
        submitted = st.form_submit_button("Analizar", type="primary")

    if submitted:
        st.session_state.pop("pending_title_search", None)
        if not query.strip():
            st.error("Introduce un ISBN o título.")
            return

        marketplace_code = marketplace_labels[marketplace_label]
        if search_mode == "ISBN":
            _run_analysis(
                settings,
                isbn=query,
                book=None,
                marketplace_code=marketplace_code,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            try:
                search_results = resolve_book_by_title(settings, query, marketplace_code)
            except BookNotFoundError as exc:
                st.error(str(exc))
                return
            except Exception as exc:
                st.error(f"Error al buscar en Google Books: {exc}")
                return

            if len(search_results) == 1:
                _run_analysis(
                    settings,
                    isbn=None,
                    book=search_results[0].metadata,
                    marketplace_code=marketplace_code,
                    start_date=start_date,
                    end_date=end_date,
                )
            else:
                st.session_state["pending_title_search"] = {
                    "results": search_results,
                    "marketplace_code": marketplace_code,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                }

    pending = st.session_state.get("pending_title_search")
    if pending:
        st.subheader("Selecciona el libro correcto")
        results: list[BookSearchResult] = pending["results"]
        choice_labels = [result.display_label for result in results]
        chosen = st.selectbox("Resultados encontrados", options=choice_labels)
        if st.button("Confirmar y analizar", type="primary"):
            selected_book = next(
                result.metadata for result in results if result.display_label == chosen
            )
            st.session_state.pop("pending_title_search", None)
            _run_analysis(
                settings,
                isbn=None,
                book=selected_book,
                marketplace_code=pending["marketplace_code"],
                start_date=date.fromisoformat(pending["start_date"]),
                end_date=date.fromisoformat(pending["end_date"]),
            )


def main() -> None:
    st.set_page_config(
        page_title="Book Sales Tracker",
        page_icon="📚",
        layout="wide",
    )
    st.title("Book Sales Tracker")

    tab_analysis, tab_compare, tab_catalog, tab_monitor = st.tabs(
        ["Análisis ISBN", "Comparador ISBN", "Catálogo editorial", "Monitor editorial"]
    )

    with tab_monitor:
        render_monitor_tab()

    with tab_catalog:
        try:
            settings = get_settings()
        except Exception as exc:
            st.error(
                "Configura `.env` con `KEEPA_API_KEY`. "
                "Para descubrir catálogo también `GOOGLE_BOOKS_API_KEY`. "
                f"Detalle: {exc}"
            )
        else:
            render_publisher_catalog_tab(settings)

    with tab_compare:
        try:
            settings = get_settings()
        except Exception as exc:
            st.error(
                "Configura `.env` con `KEEPA_API_KEY` (y opcionalmente `GOOGLE_BOOKS_API_KEY`). "
                f"Detalle: {exc}"
            )
        else:
            render_comparator_tab(settings)

    with tab_analysis:
        try:
            settings = get_settings()
        except Exception as exc:
            st.error(
                "No se pudo cargar la configuración. Crea un `.env` con "
                "`KEEPA_API_KEY` y `GEMINI_API_KEY`. "
                f"Detalle: {exc}"
            )
        else:
            _render_analysis_tab(settings)


if __name__ == "__main__":
    main()

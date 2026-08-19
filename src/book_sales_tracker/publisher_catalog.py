from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from book_sales_tracker.google_books import (
    BookNotFoundError,
    GoogleBooksError,
    search_by_publisher,
)
from book_sales_tracker.marketplace import list_marketplace_options
from book_sales_tracker.models import BookMetadata, PipelineResult
from book_sales_tracker.pipeline import PipelineError, run_pipeline


def _catalog_dataframe(books: list[BookMetadata]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "título": book.title,
                "isbn": book.isbn_13 or book.isbn_10,
                "publicación": book.published_date or "—",
                "autores": ", ".join(book.authors) if book.authors else "—",
            }
            for book in books
        ]
    )


def _performance_summary(results: list[PipelineResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        summary = result.summary
        rows.append(
            {
                "título": result.book.title,
                "isbn": result.book.isbn_13 or result.book.isbn_10,
                "publicación": result.book.published_date or "—",
                "asin": result.keepa.asin,
                "bsr_mín": summary.min_bsr,
                "bsr_máx": summary.max_bsr,
                "mejor_tramo": summary.best_tier.label_es if summary.best_tier else "—",
                "tramo_actual": summary.end_tier.label_es if summary.end_tier else "—",
                "cambios_tramo": summary.tier_changes,
                "días_bsr": summary.total_days,
            }
        )
    return pd.DataFrame(rows)


def _performance_chart(results: list[PipelineResult]):
    records = []
    for result in results:
        label = result.book.title
        if len(label) > 35:
            label = label[:32] + "…"
        for point in result.bsr_series:
            records.append(
                {"fecha": point.timestamp.date(), "bsr": point.bsr, "libro": label}
            )
    if not records:
        return None
    df = pd.DataFrame(records)
    fig = px.line(
        df,
        x="fecha",
        y="bsr",
        color="libro",
        markers=False,
        labels={"fecha": "Fecha", "bsr": "Sales rank", "libro": "Libro"},
        title="Performance BSR del catálogo",
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def render_publisher_catalog_tab(settings) -> None:
    st.subheader("Catálogo editorial")
    st.caption(
        "Busca títulos publicados por una editorial en un periodo (Google Books) "
        "y analiza su performance BSR en Amazon (Keepa)."
    )

    if not settings.google_books_api_key:
        st.warning(
            "Necesitas `GOOGLE_BOOKS_API_KEY` en `.env` para descubrir el catálogo. "
            "Mientras tanto puedes usar **Comparador ISBN** si conoces los ISBNs."
        )

    marketplace_options = list_marketplace_options()
    marketplace_labels = {label: code for code, label in marketplace_options}
    default_label = next(
        (label for code, label in marketplace_options if code == settings.default_amazon_domain),
        marketplace_options[0][1],
    )

    today = date.today()

    with st.form("publisher_catalog_search"):
        publisher = st.text_input(
            "Nombre de la editorial",
            placeholder="Libros del Asteroide, Random House, Anagrama…",
        )
        st.markdown("**Ventana de publicación** (filtro Google Books)")
        pub_cols = st.columns(2)
        pub_start = pub_cols[0].date_input(
            "Publicado desde",
            value=date(today.year - 1, 1, 1),
        )
        pub_end = pub_cols[1].date_input("Publicado hasta", value=today)

        marketplace_label = st.selectbox(
            "Marketplace Amazon (Keepa)",
            options=list(marketplace_labels.keys()),
            index=list(marketplace_labels.keys()).index(default_label),
        )
        max_titles = st.slider("Máximo de títulos a descubrir", 5, 80, 30)
        search_clicked = st.form_submit_button("Buscar catálogo", type="primary")

    if search_clicked:
        if not publisher.strip():
            st.error("Introduce el nombre de la editorial.")
            return
        if not settings.google_books_api_key:
            st.error("Configura `GOOGLE_BOOKS_API_KEY` para buscar el catálogo.")
            return

        from book_sales_tracker.marketplace import get_marketplace

        marketplace = get_marketplace(marketplace_labels[marketplace_label])
        with st.spinner(f"Buscando en Google Books: «{publisher}»…"):
            try:
                books = search_by_publisher(
                    publisher,
                    marketplace,
                    pub_start=pub_start,
                    pub_end=pub_end,
                    api_key=settings.google_books_api_key,
                    max_results=max_titles,
                )
            except (GoogleBooksError, ValueError) as exc:
                st.error(str(exc))
                return

        st.session_state["publisher_catalog"] = {
            "publisher": publisher.strip(),
            "books": books,
            "marketplace_code": marketplace.code,
            "marketplace_label": marketplace.label,
            "pub_start": pub_start.isoformat(),
            "pub_end": pub_end.isoformat(),
        }

    catalog_state = st.session_state.get("publisher_catalog")
    if not catalog_state:
        st.info("Busca una editorial para ver el catálogo y analizar performance.")
        return

    books: list[BookMetadata] = catalog_state["books"]
    st.markdown(
        f"**{catalog_state['publisher']}** — {len(books)} título(s) con ISBN "
        f"(publicación {catalog_state['pub_start']} → {catalog_state['pub_end']})"
    )

    if not books:
        st.warning(
            "No se encontraron libros con ISBN en ese periodo. "
            "Prueba ampliar fechas o ajustar el nombre de la editorial."
        )
        return

    st.dataframe(_catalog_dataframe(books), use_container_width=True, hide_index=True)

    st.markdown("#### Analizar performance BSR (Keepa)")
    perf_cols = st.columns(2)
    perf_start = perf_cols[0].date_input(
        "Performance desde",
        value=date.today() - timedelta(days=90),
        key="pub_perf_start",
    )
    perf_end = perf_cols[1].date_input(
        "Performance hasta",
        value=date.today(),
        key="pub_perf_end",
    )
    st.caption(f"Coste estimado Keepa: ~{len(books)} tokens (1 por ISBN). Sin Gemini.")

    if st.button("Analizar catálogo con Keepa", type="primary"):
        results: list[PipelineResult] = []
        errors: list[str] = []
        progress = st.progress(0.0, text="Consultando Keepa…")

        for index, book in enumerate(books):
            progress.progress(
                (index + 1) / len(books),
                text=f"{index + 1}/{len(books)} — {book.title[:40]}…",
            )
            isbn = book.isbn_13 or book.isbn_10
            try:
                result = run_pipeline(
                    settings,
                    isbn=isbn,
                    book=book,
                    marketplace_code=catalog_state["marketplace_code"],
                    start_date=perf_start,
                    end_date=perf_end,
                    include_estimate=False,
                )
                results.append(result)
            except PipelineError as exc:
                errors.append(f"{book.title}: {exc}")

        progress.empty()
        st.session_state["publisher_catalog_results"] = results
        st.session_state["publisher_catalog_errors"] = errors

    results = st.session_state.get("publisher_catalog_results") or []
    errors = st.session_state.get("publisher_catalog_errors") or []

    for message in errors:
        st.error(message)

    if not results:
        return

    st.success(f"Performance analizada — {len(results)}/{len(books)} títulos con BSR.")
    summary_df = _performance_summary(results)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    if len(results) >= 2:
        fig = _performance_chart(results[:12])
        if fig:
            st.caption("Gráfico limitado a los primeros 12 títulos con datos.")
            st.plotly_chart(fig, use_container_width=True)

    if summary_df["bsr_mín"].notna().any():
        best_idx = summary_df["bsr_mín"].idxmin()
        best = summary_df.loc[best_idx]
        st.info(
            f"**Mejor performance (BSR mínimo):** {best['título']} "
            f"(rank {int(best['bsr_mín']):,})."
        )

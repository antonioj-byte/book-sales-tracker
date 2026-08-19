from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from book_sales_tracker.google_books import (
    GoogleBooksError,
    discover_publishers,
    search_publisher_catalog,
)
from book_sales_tracker.marketplace import get_marketplace, list_marketplace_options
from book_sales_tracker.models import BookMetadata, PipelineResult, PublisherSuggestion
from book_sales_tracker.pipeline import PipelineError, run_pipeline


def _suggestion_label(item: PublisherSuggestion) -> str:
    samples = ", ".join(item.sample_titles[:2]) if item.sample_titles else "sin muestra"
    return (
        f"{item.name} — {item.volume_count} volúmenes "
        f"(coincidencia {int(item.match_score * 100)}%) · ej.: {samples}"
    )


def _catalog_dataframe(books: list[BookMetadata]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "título": book.title,
                "isbn": book.isbn_13 or book.isbn_10,
                "publicación": book.published_date or "—",
                "editorial_gb": book.publisher or "—",
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


def _render_empty_catalog_help(catalog_result, pub_start: str, pub_end: str) -> None:
    st.warning("No se encontraron libros con ISBN en ese periodo para la editorial confirmada.")
    st.markdown(
        f"- Volúmenes revisados: **{catalog_result.volumes_scanned}**\n"
        f"- Con editorial coincidente: **{catalog_result.matched_publisher}**\n"
        f"- En ventana {pub_start} → {pub_end}: **{catalog_result.in_date_range}**\n"
        f"- Con ISBN: **{catalog_result.with_isbn}**"
    )
    st.info(
        "Prueba ampliar las fechas de publicación, elige otra editorial sugerida "
        "o revisa que el nombre coincida con el registrado en Google Books."
    )


def render_publisher_catalog_tab(settings) -> None:
    st.subheader("Catálogo editorial")
    st.caption(
        "1) Confirma el nombre exacto de la editorial en Google Books. "
        "2) Carga el catálogo del periodo. 3) Analiza BSR con Keepa."
    )

    if not settings.google_books_api_key:
        st.warning(
            "Necesitas `GOOGLE_BOOKS_API_KEY` en `.env`. "
            "Mientras tanto puedes usar **Comparador ISBN**."
        )

    marketplace_options = list_marketplace_options()
    marketplace_labels = {label: code for code, label in marketplace_options}
    default_label = next(
        (label for code, label in marketplace_options if code == settings.default_amazon_domain),
        marketplace_options[0][1],
    )

    today = date.today()

    with st.form("publisher_lookup_form"):
        publisher_query = st.text_input(
            "Nombre de la editorial (búsqueda)",
            placeholder="Libros del Asteroide, Anagrama, Alfaguara…",
        )
        pub_cols = st.columns(2)
        pub_start = pub_cols[0].date_input(
            "Publicado desde",
            value=date(today.year - 3, 1, 1),
        )
        pub_end = pub_cols[1].date_input("Publicado hasta", value=today)
        marketplace_label = st.selectbox(
            "Mercado Google Books / Keepa",
            options=list(marketplace_labels.keys()),
            index=list(marketplace_labels.keys()).index(default_label),
        )
        lookup_clicked = st.form_submit_button("Buscar editoriales", type="primary")

    if lookup_clicked:
        if not publisher_query.strip():
            st.error("Introduce un nombre de editorial.")
            return
        if not settings.google_books_api_key:
            st.error("Configura `GOOGLE_BOOKS_API_KEY`.")
            return

        marketplace = get_marketplace(marketplace_labels[marketplace_label])
        with st.spinner(f"Buscando editoriales similares a «{publisher_query}»…"):
            try:
                suggestions = discover_publishers(
                    publisher_query,
                    marketplace,
                    api_key=settings.google_books_api_key,
                )
            except (GoogleBooksError, ValueError) as exc:
                st.error(str(exc))
                return

        st.session_state["publisher_suggestions"] = {
            "query": publisher_query.strip(),
            "suggestions": [item.model_dump() for item in suggestions],
            "marketplace_code": marketplace.code,
            "marketplace_label": marketplace.label,
            "pub_start": pub_start.isoformat(),
            "pub_end": pub_end.isoformat(),
        }
        st.session_state.pop("publisher_catalog", None)
        st.session_state.pop("publisher_catalog_results", None)
        st.session_state.pop("publisher_catalog_errors", None)

    suggestion_state = st.session_state.get("publisher_suggestions")
    if not suggestion_state:
        st.info("Introduce una editorial y pulsa **Buscar editoriales** para ver coincidencias.")
        return

    suggestions = [PublisherSuggestion(**item) for item in suggestion_state["suggestions"]]
    st.markdown(f"**Búsqueda:** «{suggestion_state['query']}»")

    if not suggestions:
        st.warning(
            "No encontramos editoriales parecidas en Google Books. "
            "Prueba otro nombre, menos palabras o sin acentos."
        )
        if st.button("Usar mi texto tal cual y cargar catálogo", type="primary"):
            marketplace = get_marketplace(suggestion_state["marketplace_code"])
            pub_start = date.fromisoformat(suggestion_state["pub_start"])
            pub_end = date.fromisoformat(suggestion_state["pub_end"])
            with st.spinner(f"Cargando catálogo de «{suggestion_state['query']}»…"):
                try:
                    catalog_result = search_publisher_catalog(
                        suggestion_state["query"],
                        marketplace,
                        pub_start=pub_start,
                        pub_end=pub_end,
                        api_key=settings.google_books_api_key,
                        max_results=30,
                    )
                except (GoogleBooksError, ValueError) as exc:
                    st.error(str(exc))
                    return
            st.session_state["publisher_catalog"] = {
                "publisher": suggestion_state["query"],
                "books": [book.model_dump() for book in catalog_result.books],
                "stats": catalog_result.model_dump(),
                "marketplace_code": suggestion_state["marketplace_code"],
                "marketplace_label": suggestion_state["marketplace_label"],
                "pub_start": suggestion_state["pub_start"],
                "pub_end": suggestion_state["pub_end"],
            }
            st.rerun()
        return

    st.markdown("#### Confirma la editorial")
    option_labels = [_suggestion_label(item) for item in suggestions]
    option_labels.append(f"Usar exactamente: «{suggestion_state['query']}»")

    chosen_label = st.radio(
        "Selecciona la editorial correcta",
        options=option_labels,
        index=0,
    )
    if chosen_label.startswith("Usar exactamente"):
        confirmed_publisher = suggestion_state["query"]
    else:
        chosen_index = option_labels.index(chosen_label)
        confirmed_publisher = suggestions[chosen_index].name

    max_titles = st.slider("Máximo de títulos a cargar", 5, 80, 30)

    if st.button("Cargar catálogo confirmado", type="primary"):
        if not settings.google_books_api_key:
            st.error("Configura `GOOGLE_BOOKS_API_KEY`.")
            return

        marketplace = get_marketplace(suggestion_state["marketplace_code"])
        pub_start = date.fromisoformat(suggestion_state["pub_start"])
        pub_end = date.fromisoformat(suggestion_state["pub_end"])

        with st.spinner(f"Cargando catálogo de «{confirmed_publisher}»…"):
            try:
                catalog_result = search_publisher_catalog(
                    confirmed_publisher,
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
            "publisher": confirmed_publisher,
            "books": [book.model_dump() for book in catalog_result.books],
            "stats": catalog_result.model_dump(),
            "marketplace_code": suggestion_state["marketplace_code"],
            "marketplace_label": suggestion_state["marketplace_label"],
            "pub_start": suggestion_state["pub_start"],
            "pub_end": suggestion_state["pub_end"],
        }
        st.session_state.pop("publisher_catalog_results", None)
        st.session_state.pop("publisher_catalog_errors", None)

    catalog_state = st.session_state.get("publisher_catalog")
    if not catalog_state:
        return

    books = [BookMetadata(**item) for item in catalog_state["books"]]
    stats = catalog_state.get("stats", {})

    st.markdown(
        f"**Editorial confirmada:** {catalog_state['publisher']} — "
        f"**{len(books)}** título(s) con ISBN "
        f"({catalog_state['pub_start']} → {catalog_state['pub_end']})"
    )

    if stats:
        st.caption(
            f"Google Books: {stats.get('volumes_scanned', 0)} volúmenes revisados · "
            f"{stats.get('matched_publisher', 0)} con editorial coincidente · "
            f"{stats.get('in_date_range', 0)} en periodo · "
            f"{stats.get('with_isbn', 0)} con ISBN"
        )

    if not books:
        from book_sales_tracker.models import PublisherCatalogResult

        _render_empty_catalog_help(
            PublisherCatalogResult(**stats) if stats else PublisherCatalogResult(
                publisher_confirmed=catalog_state["publisher"]
            ),
            catalog_state["pub_start"],
            catalog_state["pub_end"],
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

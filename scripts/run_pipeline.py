#!/usr/bin/env python3
"""CLI helper to run the pipeline without Streamlit."""

from datetime import date, timedelta

import typer

from book_sales_tracker.config import get_settings
from book_sales_tracker.pipeline import PipelineError, run_pipeline

app = typer.Typer(add_completion=False)


@app.command()
def analyze(
    isbn: str = typer.Option(..., help="ISBN-10 o ISBN-13"),
    marketplace: str = typer.Option("es", help="Código de marketplace Amazon"),
    start: str | None = typer.Option(None, help="Fecha inicio YYYY-MM-DD"),
    end: str | None = typer.Option(None, help="Fecha fin YYYY-MM-DD"),
) -> None:
    settings = get_settings()
    today = date.today()
    start_date = date.fromisoformat(start) if start else today - timedelta(days=90)
    end_date = date.fromisoformat(end) if end else today

    try:
        result = run_pipeline(
            settings,
            isbn=isbn,
            book=None,
            marketplace_code=marketplace,
            start_date=start_date,
            end_date=end_date,
        )
    except PipelineError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Título: {result.book.title}")
    typer.echo(f"ASIN: {result.keepa.asin}")
    typer.echo(f"Días con datos: {result.summary.total_days}")
    typer.echo(f"Rango estimado: {result.estimate.range_text}")
    typer.echo(f"Confianza: {result.estimate.confidence}")


if __name__ == "__main__":
    app()

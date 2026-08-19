import json
from pathlib import Path

from google import genai

from book_sales_tracker.config import Settings
from book_sales_tracker.models import (
    BookMetadata,
    BsrPoint,
    BsrSummary,
    KeepaProductInfo,
    SalesEstimate,
)

PROMPT_PATH = Path(__file__).parent / "prompts" / "sales_estimate_es.txt"


class LlmEstimatorError(Exception):
    pass


def _load_prompt_template() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _build_context(
    book: BookMetadata,
    marketplace_label: str,
    keepa: KeepaProductInfo,
    points: list[BsrPoint],
    summary: BsrSummary,
    date_start: str,
    date_end: str,
) -> dict:
    series_sample = [
        {
            "fecha": point.timestamp.date().isoformat(),
            "bsr": point.bsr,
            "tramo": point.tier.label_es,
        }
        for point in points[-200:]
    ]

    return {
        "libro": {
            "titulo": book.title,
            "autores": book.authors,
            "editorial": book.publisher,
            "fecha_publicacion": book.published_date,
            "categorias_google_books": book.categories,
            "isbn_13": book.isbn_13,
            "isbn_10": book.isbn_10,
        },
        "amazon": {
            "marketplace": marketplace_label,
            "asin": keepa.asin,
            "categoria_bsr_id": keepa.category_id,
            "titulo_keepa": keepa.title,
        },
        "periodo": {"inicio": date_start, "fin": date_end},
        "resumen_tramos": {
            "distribucion_porcentual": summary.tier_distribution,
            "mejor_tramo": summary.best_tier.label_es if summary.best_tier else None,
            "tramo_inicio": summary.start_tier.label_es if summary.start_tier else None,
            "tramo_fin": summary.end_tier.label_es if summary.end_tier else None,
            "cambios_de_tramo": summary.tier_changes,
            "bsr_minimo": summary.min_bsr,
            "bsr_maximo": summary.max_bsr,
            "dias_con_datos": summary.total_days,
        },
        "serie_diaria_muestra": series_sample,
        "nota": (
            "El BSR es un ranking relativo, no ventas directas. "
            "La estimación debe ser conservadora en tramos altos."
        ),
    }


def _parse_sections(text: str) -> SalesEstimate:
    sections = {
        "range_text": "",
        "confidence": "",
        "explanation": "",
    }
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Rango estimado"):
            current = "range_text"
            continue
        if stripped.startswith("## Nivel de confianza"):
            current = "confidence"
            continue
        if stripped.startswith("## Explicación"):
            current = "explanation"
            continue
        if current and stripped:
            sections[current] = (
                f"{sections[current]}\n{stripped}".strip()
                if sections[current]
                else stripped
            )

    if not any(sections.values()):
        return SalesEstimate(
            range_text="No disponible",
            confidence="No disponible",
            explanation=text.strip() or "Sin respuesta del modelo.",
            raw_response=text,
        )

    return SalesEstimate(
        range_text=sections["range_text"] or "No disponible",
        confidence=sections["confidence"] or "No disponible",
        explanation=sections["explanation"] or "No disponible",
        raw_response=text,
    )


def estimate_sales(
    settings: Settings,
    book: BookMetadata,
    marketplace_label: str,
    keepa: KeepaProductInfo,
    points: list[BsrPoint],
    summary: BsrSummary,
    date_start: str,
    date_end: str,
) -> SalesEstimate:
    context = _build_context(
        book=book,
        marketplace_label=marketplace_label,
        keepa=keepa,
        points=points,
        summary=summary,
        date_start=date_start,
        date_end=date_end,
    )
    prompt_template = _load_prompt_template()
    prompt = prompt_template.format(context_json=json.dumps(context, ensure_ascii=False, indent=2))

    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
    except Exception as exc:
        raise LlmEstimatorError(f"Error al llamar a Gemini: {exc}") from exc

    text = (response.text or "").strip()
    if not text:
        raise LlmEstimatorError("Gemini devolvió una respuesta vacía.")

    return _parse_sections(text)

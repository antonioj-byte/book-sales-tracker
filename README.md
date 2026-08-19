# Book Sales Tracker

Prototipo local que analiza la evolución del **Best Sellers Rank (BSR)** de un libro en Amazon a partir de Keepa, clasifica el ranking en tramos y genera una **estimación de ventas en lenguaje natural** con Gemini Flash-Lite.

## Requisitos

- Python 3.11+
- API keys de Keepa y Gemini (Google AI Studio)
- Google Books API key (opcional, recomendada)

## Configuración

1. Clona el repositorio y crea un entorno virtual:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copia las variables de entorno:

```bash
cp .env.example .env
```

3. Edita `.env`:

```bash
KEEPA_API_KEY=tu_clave_keepa
GEMINI_API_KEY=tu_clave_gemini
GOOGLE_BOOKS_API_KEY=tu_clave_google_books   # opcional
DEFAULT_AMAZON_DOMAIN=es
GEMINI_MODEL=gemini-3.5-flash-lite
```

## Uso (Streamlit)

```bash
PYTHONPATH=src streamlit run src/book_sales_tracker/app.py
```

En el formulario puedes introducir:

- **ISBN** o **título** (con selector si hay varios resultados)
- **Rango de fechas**
- **Marketplace Amazon** (por defecto Amazon.es)

## Uso (CLI opcional)

```bash
PYTHONPATH=src python scripts/run_pipeline.py --isbn 9788410178595 --marketplace es
```

## ISBN de prueba

- ISBN-13: `9788410178595`
- ISBN-10: `8410178591`
- Marketplace recomendado: **Amazon.es**

## Pipeline

1. **Google Books** — metadatos y validación del libro
2. **Keepa** — resolución ISBN→ASIN e histórico BSR (sin scraping de Amazon)
3. **Procesamiento** — filtro por fechas, agregación diaria y clasificación en 11 tramos BSR
4. **Gemini Flash-Lite** — estimación en español (rango + confianza + explicación)

## Tramos BSR

| Tramo | BSR |
|-------|-----|
| Top 10 | 1–10 |
| Top 100 | 11–100 |
| Top 500 | 101–500 |
| Top 1.000 | 501–1.000 |
| Top 5.000 | 1.001–5.000 |
| Top 10.000 | 5.001–10.000 |
| Top 50.000 | 10.001–50.000 |
| Top 100.000 | 50.001–100.000 |
| Top 150.000 | 100.001–150.000 |
| Más de 150.000 | >150.000 |

## Coste aproximado por consulta

- Keepa: ~1 token
- Google Books: gratis / cuota generosa
- Gemini Flash-Lite: fracciones de céntimo

## Notas

- No se scrapea Amazon; todo el histórico BSR proviene de Keepa.
- El BSR es un ranking relativo, no una cifra directa de ventas.
- El ASIN puede variar según marketplace; si un ISBN no existe en Amazon.es, prueba otro marketplace.

# Keepa Monitor — Fase 1

Monitor diario de rankings Amazon vía Keepa (módulo relativo por editorial + módulo absoluto por categoría).

## Setup

```bash
cd keepa-monitor
pip install -r requirements.txt
cp .env.example .env   # o reutiliza KEEPA_API_KEY del .env raíz
python scripts/setup_db.py
python scripts/daily_fetch.py
```

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `KEEPA_API_KEY` | Obligatoria |
| `MAX_TOKENS_PER_RUN` | Presupuesto diario (default 150) |
| `DEFAULT_KEEPA_DOMAIN` | Mercado para ASINs relativos (9 = Amazon.es) |
| `CATEGORY_TREE_REFRESH_DAYS` | Refresh de category_tree (default 30) |
| `BEST_SELLERS_TOP_N` | Recorte top N (default 100) |

## Cron (ejemplo)

```cron
0 7 * * * cd /ruta/keepa-monitor && python scripts/daily_fetch.py >> logs/cron.log 2>&1
```

## Verificación SQL

```bash
sqlite3 db/keepa_monitor.db "SELECT * FROM fetch_runs ORDER BY id DESC LIMIT 1;"
sqlite3 db/keepa_monitor.db "SELECT snapshot_date, asin, sales_rank, price_cents FROM rank_snapshots_relative ORDER BY snapshot_date DESC LIMIT 10;"
sqlite3 db/keepa_monitor.db "SELECT snapshot_date, category_name, rank_position, asin FROM rank_snapshots_absolute ORDER BY snapshot_date DESC, rank_position LIMIT 10;"
```

## Coste tokens (aprox./día)

- 1 token / ASIN (batch en una llamada)
- 50 tokens / categoría best sellers
- 2 tokens / category_lookup (solo cada 30 días)

## Rama de respaldo

El prototipo Streamlit con **7 tramos BSR** está preservado en la rama `cursor/book-sales-tracker-stable-abfc`.

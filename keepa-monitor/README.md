# Keepa Monitor MVP

Monitor diario de rankings Amazon vía Keepa:

- **Módulo relativo** — evolución BSR de ASINs propios vs escauteados (misma editorial)
- **Módulo absoluto** — top 100 por categoría (entradas, salidas, movimientos grandes)

## Setup

```bash
cd keepa-monitor
pip install -r requirements.txt
cp .env.example .env   # o reutiliza KEEPA_API_KEY del .env raíz
python scripts/setup_db.py
python scripts/daily_fetch.py
python scripts/compute_deltas.py
python scripts/report.py
```

## Pipeline diario

| Paso | Script | API Keepa |
|------|--------|-----------|
| 1 | `setup_db.py` | No |
| 2 | `daily_fetch.py` | Sí |
| 3 | `compute_deltas.py` | No |
| 4 | `detect_jumps.py` | No |
| 5 | `report.py` | No |

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `KEEPA_API_KEY` | Obligatoria para `daily_fetch.py` |
| `MAX_TOKENS_PER_RUN` | Presupuesto diario (default 150) |
| `DEFAULT_KEEPA_DOMAIN` | Mercado para ASINs relativos (9 = Amazon.es) |
| `CATEGORY_TREE_REFRESH_DAYS` | Refresh de category_tree (default 30) |
| `BEST_SELLERS_TOP_N` | Recorte top N (default 100) |
| `DELTA_THRESHOLD_PCT` | Umbral alerta relativa (default 80 %) |
| `POSITION_MOVE_THRESHOLD` | Movimiento mínimo en top 100 (default 30 pos.) |
| `LOOKBACK_DAYS` | Ventanas de comparación (default `7,30`) |
| `REPORT_DAYS` | Días hacia atrás en informe (default 7) |

## Cron (ejemplo)

```cron
0 7 * * * cd /ruta/keepa-monitor && python scripts/daily_fetch.py >> logs/cron.log 2>&1
15 7 * * * cd /ruta/keepa-monitor && python scripts/compute_deltas.py >> logs/cron.log 2>&1
20 7 * * * cd /ruta/keepa-monitor && python scripts/report.py --output reports/daily.md >> logs/cron.log 2>&1
```

## Alertas (Fase 2)

**Relativas** (por ASIN editorial):
- Delta BSR ≥ `DELTA_THRESHOLD_PCT` en ventanas de 7 y 30 días

**Absolutas** (por categoría):
- Entrada / salida del top 100
- Movimiento ≥ `POSITION_MOVE_THRESHOLD` posiciones entre snapshots

### Saltos importantes (`detect_jumps.py`)

Detección dedicada sobre el top 100 por categoría (offline, sin API extra):

| Tipo | Descripción | Severidad |
|------|-------------|-----------|
| `new_entrant_top10` | Nuevo en top 100 directamente en top 10 | alta |
| `new_entrant_top20` | Nuevo en top 11–20 | alta |
| `new_entrant` | Nuevo en top 21–100 | media |
| `entered_top10` / `entered_top20` | Subió desde dentro del top 100 | alta |
| `surge_up` / `surge_down` | Movimiento ≥ 30 posiciones | alta/media |

```bash
# Amazon.es (mercado 9), comparando 7 días
python scripts/detect_jumps.py --markets 9 --lookback-days 7

# Dos mercados (requiere filas en categories.csv con mercado=9 y mercado=1)
python scripts/detect_jumps.py --markets 9,1 --min-severity high

# Solo Literatura y ficción
python scripts/detect_jumps.py --categories 902689031 --format json

# Guardar en alerts
python scripts/detect_jumps.py --write-alerts --output reports/jumps.txt
```

> Con un solo día de datos no hay comparables; los saltos aparecen tras acumular histórico diario.

## Verificación SQL

```bash
sqlite3 db/keepa_monitor.db "SELECT * FROM fetch_runs ORDER BY id DESC LIMIT 1;"
sqlite3 db/keepa_monitor.db "SELECT snapshot_date, asin, sales_rank FROM rank_snapshots_relative ORDER BY snapshot_date DESC LIMIT 10;"
sqlite3 db/keepa_monitor.db "SELECT snapshot_date, category_name, rank_position, asin FROM rank_snapshots_absolute ORDER BY snapshot_date DESC, rank_position LIMIT 10;"
sqlite3 db/keepa_monitor.db "SELECT alert_date, module, alert_type, message FROM alerts ORDER BY id DESC LIMIT 10;"
```

## Informes

```bash
python scripts/report.py                          # markdown a stdout
python scripts/report.py --format text            # texto plano
python scripts/report.py --format csv --output reports/alerts.csv
python scripts/report.py --days 14 --output reports/weekly.md
```

## Coste tokens (aprox./día)

- 1 token / ASIN (batch en una llamada)
- 50 tokens / categoría best sellers
- 2 tokens / category_lookup (solo cada 30 días)

Con la config de ejemplo (2 ASINs + 2 categorías): **~102 tokens/día**.

## Rama de respaldo

El prototipo Streamlit con **7 tramos BSR** está preservado en la rama `cursor/book-sales-tracker-stable-abfc`.

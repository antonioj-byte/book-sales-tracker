from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from lib.config import DEFAULT_DB_PATH, get_settings  # noqa: E402
from lib.db import SCHEMA_SQL, connect, init_schema  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Inicializa la base SQLite de keepa-monitor")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Ruta al archivo SQLite",
    )
    args = parser.parse_args()

    settings = get_settings(db_path=args.db_path)
    conn = connect(settings.db_path)
    init_schema(conn)

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print(f"Base de datos inicializada: {settings.db_path}")
    print("Tablas creadas:")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) AS c FROM {table['name']}").fetchone()["c"]
        print(f"  - {table['name']} ({count} filas)")

    print("\nEsquema principal:")
    print(SCHEMA_SQL.strip().split("CREATE INDEX")[0])


if __name__ == "__main__":
    main()

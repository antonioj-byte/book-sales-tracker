from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from lib.config import get_monitor_settings  # noqa: E402
from lib.db import connect, init_schema  # noqa: E402
from lib.deltas import run_delta_computation  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calcula deltas y alertas desde SQLite (sin llamadas a Keepa)"
    )
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    settings = get_monitor_settings(db_path=args.db_path)
    conn = connect(settings.db_path)
    init_schema(conn)

    result = run_delta_computation(conn, settings)
    conn.close()

    print("compute_deltas completado:")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()

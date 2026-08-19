import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

from lib.config import MonitorSettings
from lib.db import init_schema, insert_absolute_snapshot
from lib.jumps import JumpSeverity, JumpType, detect_category_jumps


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    init_schema(connection)
    yield connection
    connection.close()


def _settings() -> MonitorSettings:
    return MonitorSettings(
        db_path=Path("test.db"),
        default_keepa_domain=9,
        max_tokens_per_run=150,
        category_tree_refresh_days=30,
        best_sellers_top_n=100,
        delta_threshold_pct=80,
        position_move_threshold=30,
        lookback_days=(7, 30),
        report_days=7,
    )


def _seed_absolute(conn, snapshot_date: str, domain_id: int, category_id: str, asin_ranks: dict[str, int]):
    for asin, position in asin_ranks.items():
        insert_absolute_snapshot(
            conn,
            {
                "snapshot_date": snapshot_date,
                "domain_id": domain_id,
                "category_id": category_id,
                "category_name": "Literatura y ficción",
                "rank_position": position,
                "asin": asin,
                "fetched_at": "2026-08-19T00:00:00+00:00",
            },
        )
    conn.commit()


def test_detect_new_entrant_top10(conn):
    today = "2026-08-19"
    before = "2026-08-12"
    cat = "902689031"
    _seed_absolute(conn, before, 9, cat, {"A": 1, "B": 2, "C": 3})
    _seed_absolute(conn, today, 9, cat, {"A": 1, "NEWBOOK": 5, "B": 2})

    jumps = detect_category_jumps(
        conn, _settings(), snapshot_today=today, lookback_days=7, domain_ids=(9,)
    )
    types = {jump.jump_type for jump in jumps}
    assert JumpType.NEW_ENTRANT_TOP10 in types
    assert any(jump.asin == "NEWBOOK" for jump in jumps)


def test_detect_surge_up(conn):
    today = "2026-08-19"
    before = "2026-08-12"
    cat = "902689031"
    _seed_absolute(conn, before, 9, cat, {"A": 1, "CLIMBER": 80, "B": 2})
    _seed_absolute(conn, today, 9, cat, {"A": 1, "CLIMBER": 25, "B": 2})

    jumps = detect_category_jumps(
        conn, _settings(), snapshot_today=today, lookback_days=7, domain_ids=(9,)
    )
    surge = [jump for jump in jumps if jump.asin == "CLIMBER"]
    assert surge
    assert surge[0].jump_type == JumpType.SURGE_UP
    assert surge[0].positions_delta == -55


def test_filter_by_market(conn):
    today = "2026-08-19"
    before = "2026-08-12"
    cat = "902689031"
    _seed_absolute(conn, before, 9, cat, {"A": 1})
    _seed_absolute(conn, today, 9, cat, {"A": 1, "ESNEW": 8})
    _seed_absolute(conn, before, 1, cat, {"A": 1})
    _seed_absolute(conn, today, 1, cat, {"A": 1, "USNEW": 8})

    jumps_es = detect_category_jumps(
        conn, _settings(), snapshot_today=today, lookback_days=7, domain_ids=(9,)
    )
    assert all(jump.domain_id == 9 for jump in jumps_es)
    assert any(jump.asin == "ESNEW" for jump in jumps_es)
    assert not any(jump.asin == "USNEW" for jump in jumps_es)

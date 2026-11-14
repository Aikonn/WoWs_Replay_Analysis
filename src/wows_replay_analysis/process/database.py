"""SQLite database with one row per match from the recording player's perspective.

File: data/stats.sqlite. Open it with the VS Code SQLite extension to explore.
The database can always be rebuilt from data/raw/.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from wows_replay_analysis.config import Config
from wows_replay_analysis.process import PROCESSOR_VERSION
from wows_replay_analysis.process.raw_loader import list_raw_matches, load_raw_match
from wows_replay_analysis.process.stats import match_stats_row

logger = logging.getLogger(__name__)

MIGRATION_COLUMNS = {
    "replay_complete": "INTEGER",
    "end_reason": "TEXT",
    "recorded_s": "REAL",
    "stats_source": "TEXT",
}

# First version of the schema. Add columns rather than rename them, and bump
# PROCESSOR_VERSION when it changes.
SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id            TEXT PRIMARY KEY,
    processor_version   INTEGER NOT NULL,
    played_at           TEXT NOT NULL,      -- ISO 8601, local time from the replay
    game_version        TEXT,
    map_name            TEXT,
    match_group         TEXT,               -- pvp, ranked, clan, pve, ...
    scenario            TEXT,               -- e.g. domination_3point
    player_name         TEXT,
    ship_name           TEXT,
    ship_class          TEXT,               -- Destroyer, Cruiser, Battleship, AirCarrier, Submarine
    ship_tier           INTEGER,
    result              TEXT,               -- win, loss, draw, unknown (replay ended early)
    duration_s          REAL,
    survived            INTEGER,            -- 0/1
    time_of_death_s     REAL,               -- NULL if survived
    damage              INTEGER,
    frags               INTEGER,
    spotting_damage     INTEGER,
    potential_damage    REAL,
    damage_received     INTEGER,
    base_xp             INTEGER,
    planes_killed       INTEGER,
    capture_points      INTEGER,
    defense_points      INTEGER,
    ribbons_json        TEXT,               -- {"RIBBON_TORPEDO": 8, ...}
    replay_complete     INTEGER,            -- 0/1, see stats.replay_end()
    end_reason          TEXT,               -- battle_end, left_after_death, disconnected, unknown
    recorded_s          REAL,               -- seconds of battle the replay covers
    stats_source        TEXT                -- report (exact) or timeline (estimated)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open (and create if needed) the database and apply SCHEMA."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SCHEMA)
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(matches)")
        }
        for name, definition in MIGRATION_COLUMNS.items():
            if name not in columns:
                connection.execute(f'ALTER TABLE matches ADD COLUMN "{name}" {definition}')
        connection.commit()
    except Exception:
        connection.close()
        raise
    return connection


def upsert_match(conn: sqlite3.Connection, row: dict) -> None:
    """Insert or replace one match row."""
    table_columns = {
        record["name"] for record in conn.execute("PRAGMA table_info(matches)")
    }
    columns = list(row)
    if "match_id" not in row:
        raise ValueError("A match row must include match_id")
    if set(columns) != table_columns:
        missing = sorted(table_columns - set(columns))
        extra = sorted(set(columns) - table_columns)
        raise ValueError(f"Invalid match row columns (missing={missing}, extra={extra})")

    column_sql = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(
        f'"{column}" = excluded."{column}"'
        for column in columns
        if column != "match_id"
    )
    conn.execute(
        f"INSERT INTO matches ({column_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT(match_id) DO UPDATE SET {updates}",
        [row[column] for column in columns],
    )


def rebuild_database(config: Config, force: bool = False) -> int:
    """Add rows for all raw extracts that are missing or outdated in the database.

    Return the number of rows written.

    Skip matches excluded by selection.is_included(raw, config.match_groups)
    and delete their existing rows, so the database only holds the selected
    battle types (it is derived data and can always be rebuilt).
    """
    connection = connect(config.database_path)
    written = 0
    try:
        for match_dir in list_raw_matches(config.raw_dir):
            try:
                existing = connection.execute(
                    "SELECT processor_version FROM matches WHERE match_id = ?",
                    (match_dir.name,),
                ).fetchone()
                if (
                    not force
                    and existing is not None
                    and existing["processor_version"] >= PROCESSOR_VERSION
                ):
                    continue

                raw = load_raw_match(match_dir)
                row = match_stats_row(raw)
                with connection:
                    upsert_match(connection, row)
                written += 1
            except Exception:
                logger.exception("Could not process raw match %s", match_dir.name)
    finally:
        connection.close()
    return written

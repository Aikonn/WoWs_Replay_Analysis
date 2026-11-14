"""SQLite database with one row per match from the recording player's perspective.

File: data/stats.sqlite. Open it with the VS Code SQLite extension to explore.
The database can always be rebuilt from data/raw/.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from wows_replay_analysis.config import Config

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
    result              TEXT,               -- win, loss, draw
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
    ribbons_json        TEXT                -- {"RIBBON_TORPEDO": 8, ...}
);
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open (and create if needed) the database and apply SCHEMA."""
    raise NotImplementedError


def upsert_match(conn: sqlite3.Connection, row: dict) -> None:
    """Insert or replace one match row."""
    raise NotImplementedError


def rebuild_database(config: Config, force: bool = False) -> int:
    """Add rows for all raw extracts that are missing or outdated in the database.

    Return the number of rows written.
    """
    raise NotImplementedError

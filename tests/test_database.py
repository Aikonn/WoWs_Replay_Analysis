from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wows_replay_analysis.config import Config
from wows_replay_analysis.process import PROCESSOR_VERSION
from wows_replay_analysis.process import database


def sample_row(match_id: str, processor_version: int = PROCESSOR_VERSION) -> dict:
    return {
        "match_id": match_id,
        "processor_version": processor_version,
        "played_at": "2026-11-13 18:42:44",
        "game_version": "15,10,0,13533378",
        "map_name": "Shards",
        "match_group": "pvp",
        "scenario": "domination_3point",
        "player_name": "Captain",
        "ship_name": "Ship",
        "ship_class": "Cruiser",
        "ship_tier": 8,
        "result": "win",
        "duration_s": 800.0,
        "survived": 1,
        "time_of_death_s": None,
        "damage": 40000,
        "frags": 2,
        "spotting_damage": 6000,
        "potential_damage": 200000.0,
        "damage_received": 12000,
        "base_xp": 1400,
        "planes_killed": 3,
        "capture_points": 12,
        "defense_points": 4,
        "ribbons_json": "{}",
        "replay_complete": 1,
        "end_reason": "battle_end",
        "recorded_s": 800.0,
        "stats_source": "report",
    }


def test_connect_creates_database_and_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "stats.sqlite"

    connection = database.connect(database_path)
    try:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(matches)")
        }
    finally:
        connection.close()

    assert database_path.is_file()
    assert "match_id" in columns
    assert "ribbons_json" in columns
    assert {
        "replay_complete",
        "end_reason",
        "recorded_s",
        "stats_source",
    }.issubset(columns)


def test_connect_adds_incomplete_replay_columns_to_existing_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "existing.sqlite"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE matches (match_id TEXT PRIMARY KEY)")
    connection.commit()
    connection.close()

    connection = database.connect(database_path)
    try:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(matches)")
        }
    finally:
        connection.close()

    assert {
        "replay_complete",
        "end_reason",
        "recorded_s",
        "stats_source",
    }.issubset(columns)


def test_upsert_match_inserts_and_updates_row(tmp_path: Path) -> None:
    connection = database.connect(tmp_path / "stats.sqlite")
    try:
        database.upsert_match(connection, sample_row("match"))
        with connection:
            database.upsert_match(connection, {**sample_row("match"), "damage": 50000})

        rows = connection.execute(
            "SELECT match_id, damage FROM matches"
        ).fetchall()
    finally:
        connection.close()

    assert [tuple(row) for row in rows] == [("match", 50000)]


def test_upsert_match_rejects_missing_columns(tmp_path: Path) -> None:
    connection = database.connect(tmp_path / "stats.sqlite")
    try:
        with pytest.raises(ValueError, match="Invalid match row columns"):
            database.upsert_match(connection, {"match_id": "match"})
    finally:
        connection.close()


def test_rebuild_database_skips_current_rows_and_rebuilds_when_forced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = Config(tmp_path, tmp_path / "data", tmp_path / "cache")
    raw_dirs = [config.raw_dir / "current", config.raw_dir / "new"]
    for path in raw_dirs:
        path.mkdir(parents=True)
    connection = database.connect(config.database_path)
    try:
        database.upsert_match(connection, sample_row("current"))
        connection.commit()
    finally:
        connection.close()

    loaded: list[str] = []
    monkeypatch.setattr(database, "list_raw_matches", lambda _: raw_dirs)
    monkeypatch.setattr(database, "load_raw_match", lambda path: loaded.append(path.name) or path)
    monkeypatch.setattr(
        database,
        "match_stats_row",
        lambda raw: sample_row(raw.name, processor_version=PROCESSOR_VERSION),
    )

    assert database.rebuild_database(config) == 1
    assert loaded == ["new"]

    loaded.clear()
    assert database.rebuild_database(config, force=True) == 2
    assert loaded == ["current", "new"]


def test_rebuild_database_continues_after_bad_raw_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = Config(tmp_path, tmp_path / "data", tmp_path / "cache")
    raw_dirs = [config.raw_dir / "bad", config.raw_dir / "good"]
    for path in raw_dirs:
        path.mkdir(parents=True)
    monkeypatch.setattr(database, "list_raw_matches", lambda _: raw_dirs)

    def load(path: Path) -> Path:
        if path.name == "bad":
            raise ValueError("invalid extract")
        return path

    monkeypatch.setattr(database, "load_raw_match", load)
    monkeypatch.setattr(database, "match_stats_row", lambda raw: sample_row(raw.name))

    assert database.rebuild_database(config) == 1
    connection = sqlite3.connect(config.database_path)
    try:
        assert connection.execute("SELECT match_id FROM matches").fetchall() == [("good",)]
    finally:
        connection.close()

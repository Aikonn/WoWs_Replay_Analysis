from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest

from wows_replay_analysis.process.raw_loader import (
    RawMatch,
    list_raw_matches,
    load_raw_match,
    own_entity_ids,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def make_raw_match(
    match_dir: Path,
    *,
    errors: dict[str, str] | None = None,
    report: dict | None = None,
    timeline: dict | None = None,
) -> None:
    match_dir.mkdir(parents=True)
    write_json(
        match_dir / "meta.json",
        {"match_id": match_dir.name, "errors": errors or {}},
    )
    if report is not None:
        write_json(match_dir / "report.json", report)
    if timeline is not None:
        with gzip.open(match_dir / "timeline.json.gz", "wt", encoding="utf-8") as file:
            json.dump(timeline, file)


def test_load_raw_match_reads_report_and_optional_gzip_timeline(tmp_path: Path) -> None:
    match_dir = tmp_path / "match"
    report = {"hidden": {"player_id": 12}}
    timeline = {"events": [{"timestamp": 1.0}]}
    make_raw_match(match_dir, report=report, timeline=timeline)

    loaded = load_raw_match(match_dir)
    report_only = load_raw_match(match_dir, with_timeline=False)

    assert loaded.match_id == "match"
    assert loaded.report == report
    assert loaded.timeline == timeline
    assert report_only.report == report
    assert report_only.timeline is None


def test_load_raw_match_uses_meta_errors_for_failed_parsers(tmp_path: Path) -> None:
    match_dir = tmp_path / "partial"
    make_raw_match(match_dir, errors={"report": "unsupported version", "timeline": "failed"})

    loaded = load_raw_match(match_dir)

    assert loaded.report is None
    assert loaded.timeline is None


def test_load_raw_match_rejects_malformed_json(tmp_path: Path) -> None:
    match_dir = tmp_path / "broken"
    match_dir.mkdir()
    (match_dir / "meta.json").write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON"):
        load_raw_match(match_dir)


def test_list_raw_matches_includes_only_extracts_oldest_first(tmp_path: Path) -> None:
    older = tmp_path / "older"
    newer = tmp_path / "newer"
    backup = tmp_path / ".old.backup"
    make_raw_match(older)
    make_raw_match(newer)
    make_raw_match(backup)
    (tmp_path / "incomplete").mkdir()
    os.utime(older / "meta.json", (10, 10))
    os.utime(newer / "meta.json", (20, 20))

    assert list_raw_matches(tmp_path) == [older, newer]
    assert list_raw_matches(tmp_path / "missing") == []


def test_own_entity_ids_matches_avatar_not_account_or_ship_id() -> None:
    raw = RawMatch(
        "match",
        {},
        {
            "hidden": {
                "player_id": 777,
                "players": {
                    "1": {"avatarId": 111, "shipId": 222},
                    "2": {"avatarId": 777, "shipId": 888},
                },
            }
        },
        None,
    )

    assert own_entity_ids(raw) == (777, 888)


def test_own_entity_ids_explains_when_player_is_missing() -> None:
    raw = RawMatch("match", {}, {"hidden": {"player_id": 777, "players": {}}}, None)

    with pytest.raises(ValueError, match="No report player"):
        own_entity_ids(raw)

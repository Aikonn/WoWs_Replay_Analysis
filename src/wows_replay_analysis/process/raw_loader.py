"""Loads one raw extract (data/raw/<match_id>/) into memory.

Shared by match_summary.py and stats.py so both read the files the same way.
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RawMatch:
    """Everything Stage 1 stored for one match.

    report or timeline is None if that parser failed during extraction
    (see meta["errors"]).
    """

    match_id: str
    meta: dict
    report: dict | None
    timeline: dict | None


def load_raw_match(match_dir: Path, with_timeline: bool = True) -> RawMatch:
    """Read meta.json, report.json and (optionally) timeline.json.gz.

    The timeline is large (about 27 MB uncompressed); pass with_timeline=False
    when only the post-battle report is needed.
    """
    meta = _read_json_object(match_dir / "meta.json")
    errors = meta.get("errors", {})
    if not isinstance(errors, dict):
        raise ValueError(f"Invalid errors field in {match_dir / 'meta.json'}")

    report_path = match_dir / "report.json"
    if errors.get("report"):
        report = None
    else:
        report = _read_json_object(report_path)

    timeline: dict | None = None
    if with_timeline:
        timeline_path = match_dir / "timeline.json.gz"
        if errors.get("timeline"):
            timeline = None
        else:
            try:
                with gzip.open(timeline_path, "rt", encoding="utf-8") as timeline_file:
                    value = json.load(timeline_file)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError(f"Invalid JSON in {timeline_path}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected a JSON object in {timeline_path}")
            timeline = value

    match_id = meta.get("match_id", match_dir.name)
    if not isinstance(match_id, str):
        raise ValueError(f"Invalid match_id in {match_dir / 'meta.json'}")
    logger.debug("Loaded raw match %s", match_id)
    return RawMatch(match_id=match_id, meta=meta, report=report, timeline=timeline)


def list_raw_matches(raw_dir: Path) -> list[Path]:
    """Return all complete extract folders (those that contain meta.json), oldest first."""
    if not raw_dir.is_dir():
        return []
    return sorted(
        (
            path for path in raw_dir.iterdir()
            if not path.name.startswith(".")
            and path.is_dir()
            and (path / "meta.json").is_file()
        ),
        key=lambda path: (path.joinpath("meta.json").stat().st_mtime, path.name.casefold()),
    )


def own_entity_ids(raw: RawMatch) -> tuple[int, int]:
    """Return (avatar_entity_id, ship_entity_id) of the player who recorded the replay.

    In report["hidden"]: player_id is the avatar id; the matching entry in
    "players" (avatarId == player_id) has the ship entity id in "shipId".
    Timeline events refer to ships by that ship entity id.
    """
    if raw.report is None:
        raise ValueError(f"Cannot identify the recording player in {raw.match_id}: report is missing")

    hidden = raw.report.get("hidden")
    if not isinstance(hidden, dict):
        raise ValueError(f"Invalid hidden report data in {raw.match_id}")
    avatar_id = hidden.get("player_id")
    players = hidden.get("players")
    if isinstance(avatar_id, bool) or not isinstance(avatar_id, int):
        raise ValueError(f"Invalid recording player id in {raw.match_id}")
    if isinstance(players, dict):
        player_entries = players.values()
    elif isinstance(players, list):
        player_entries = players
    else:
        raise ValueError(f"Invalid players in report for {raw.match_id}")

    for player in player_entries:
        if not isinstance(player, dict) or player.get("avatarId") != avatar_id:
            continue
        ship_id = player.get("shipId")
        if isinstance(ship_id, bool) or not isinstance(ship_id, int):
            raise ValueError(f"Invalid shipId for recording player in {raw.match_id}")
        return avatar_id, ship_id
    raise ValueError(f"No report player has avatarId {avatar_id} in {raw.match_id}")


def _read_json_object(path: Path) -> dict:
    """Read one UTF-8 JSON object and reject non-object top-level values."""
    try:
        with path.open("r", encoding="utf-8") as json_file:
            value = json.load(json_file)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value

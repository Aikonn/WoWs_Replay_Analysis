"""Loads one raw extract (data/raw/<match_id>/) into memory.

Shared by match_summary.py and stats.py so both read the files the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    raise NotImplementedError


def list_raw_matches(raw_dir: Path) -> list[Path]:
    """Return all complete extract folders (those that contain meta.json), oldest first."""
    raise NotImplementedError


def own_entity_ids(raw: RawMatch) -> tuple[int, int]:
    """Return (avatar_entity_id, ship_entity_id) of the player who recorded the replay.

    In report["hidden"]: player_id is the avatar id; the matching entry in
    "players" (avatarId == player_id) has the ship entity id in "shipId".
    Timeline events refer to ships by that ship entity id.
    """
    raise NotImplementedError

"""Keeps the local wows-render-gamedata clone in sync with each replay's game build.

Repo: https://github.com/toalba/wows-render-gamedata (about 460 MB).
Tags are named v<build_id>, e.g. v13533378 for game version 15,10,0,13533378.
wows_replay_parser.gamedata_sync.sync_gamedata() already does most of this;
prefer calling it over re-implementing git handling.
"""

from __future__ import annotations

from pathlib import Path


def build_id_from_version(game_version: str) -> str:
    """Return the build id from a version string like "15,10,0,13533378" -> "13533378"."""
    raise NotImplementedError


def ensure_gamedata(gamedata_dir: Path, game_version: str) -> Path:
    """Make sure gamedata_dir is a clone checked out at the tag for game_version.

    Clone the repo if gamedata_dir does not exist. Fetch tags if the needed tag
    is missing. Return the entity_defs path:
    gamedata_dir / "data" / "scripts_entity" / "entity_defs".
    """
    raise NotImplementedError


def current_tag(gamedata_dir: Path) -> str | None:
    """Return the tag currently checked out in gamedata_dir, or None."""
    raise NotImplementedError

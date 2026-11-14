"""Keeps the local wows-render-gamedata clone in sync with each replay's game build.

Repo: https://github.com/toalba/wows-render-gamedata (about 460 MB).
Tags are named v<build_id>, e.g. v13533378 for game version 15,10,0,13533378.
wows_replay_parser.gamedata_sync.sync_gamedata() already does most of this;
prefer calling it over re-implementing git handling.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from wows_replay_parser.gamedata_sync import sync_gamedata

logger = logging.getLogger(__name__)


def build_id_from_version(game_version: str) -> str:
    """Return the build id from a version string like "15,10,0,13533378" -> "13533378"."""
    parts = game_version.replace(".", ",").split(",")
    if len(parts) < 4 or not parts[-1].strip().isdigit():
        raise ValueError(f"Game version does not contain a numeric build id: {game_version!r}")
    return parts[-1].strip()


def ensure_gamedata(gamedata_dir: Path, game_version: str) -> Path:
    """Make sure gamedata_dir is a clone checked out at the tag for game_version.

    Clone the repo if gamedata_dir does not exist. Fetch tags if the needed tag
    is missing. Return the entity_defs path:
    gamedata_dir / "data" / "scripts_entity" / "entity_defs".
    """
    build_id = build_id_from_version(game_version)
    if not sync_gamedata(gamedata_dir, game_version, auto_clone=True):
        raise RuntimeError(f"Could not sync gamedata for build {build_id} in {gamedata_dir}")

    # The helper may fall back to a neighboring tag; extraction requires an exact build match.
    expected_tag = f"v{build_id}"
    actual_tag = current_tag(gamedata_dir)
    if actual_tag != expected_tag:
        raise RuntimeError(
            f"Gamedata is checked out at {actual_tag or 'an unknown revision'}, "
            f"but replay build {build_id} requires {expected_tag}"
        )

    entity_defs = gamedata_dir / "data" / "scripts_entity" / "entity_defs"
    if not entity_defs.is_dir():
        raise FileNotFoundError(f"Gamedata entity definitions not found: {entity_defs}")
    return entity_defs


def current_tag(gamedata_dir: Path) -> str | None:
    """Return the tag currently checked out in gamedata_dir, or None."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=gamedata_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("Could not read gamedata tag in %s: %s", gamedata_dir, exc)
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None

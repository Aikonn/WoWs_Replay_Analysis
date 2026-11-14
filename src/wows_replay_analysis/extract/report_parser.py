"""Wrapper around Monstrofil/replays_unpack (post-battle report).

Install from GitHub (see pyproject.toml); the PyPI release lags behind game versions.

Note: the convenient ReplayParser class lives in the repo's top-level script
replay_parser.py, which is NOT part of the installed package. Re-implement its
get_info() here with the package classes (about 15 lines):

    from replay_unpack.replay_reader import ReplayReader
    from replay_unpack.clients import wows

    replay = ReplayReader(path).get_replay_data()
    version = replay.engine_data["clientVersionFromXml"].replace(" ", "").split(",")
    player = wows.ReplayPlayer(version)
    player.play(replay.decrypted_data, strict_mode=False)
    hidden = player.get_info()

Useful keys in `hidden`: players, battle_result, damage_map, shots_damage_map,
death_map, death_info, crew, arena_id, ribbons, achievements and
battle_results_beta (the full post-battle screen with named fields).
"""

from __future__ import annotations

from pathlib import Path


def parse_report(replay_path: Path) -> dict:
    """Parse a replay and return {"open": ..., "extra_data": ..., "hidden": ..., "error": ...}.

    Same structure as replays_unpack's CLI output. Values that are not JSON
    serialisable (bytes, custom objects) must be converted to strings, like the
    CLI's DefaultEncoder does.

    Raise an exception if the game version is not supported (RuntimeError from
    replays_unpack), so the caller can record the error.
    """
    raise NotImplementedError


def parser_version() -> str:
    """Return the installed replays_unpack version (importlib.metadata)."""
    raise NotImplementedError

"""Orchestrates Stage 1: find replays, skip already extracted ones, run both parsers.

Output per replay, in data/raw/<match_id>/ (see README "Data layout"):
    meta.json         Replay header + extraction info (written LAST, marks success).
    report.json       Post-battle report from replays_unpack.
    timeline.json.gz  Event timeline from wows-replay-parser, gzip-compressed.

match_id is the replay file name without extension,
e.g. "20261113_184244_PRSS110-K-type_23_Shards".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from wows_replay_analysis.config import Config


@dataclass
class ExtractResult:
    """Counts for the summary printed at the end of a run."""

    extracted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)  # match_id -> error message


def find_replays(replays_dir: Path) -> list[Path]:
    """Return all *.wowsreplay files in replays_dir, oldest first.

    Ignore temp.wowsreplay (the game writes it during a running battle).
    """
    raise NotImplementedError


def match_id_for(replay_path: Path) -> str:
    """Return the match id (file name without extension) for a replay."""
    raise NotImplementedError


def needs_extraction(match_dir: Path) -> bool:
    """True if the replay must be (re-)extracted.

    That is the case when meta.json is missing, unreadable, or its
    extractor_version is lower than EXTRACTOR_VERSION.
    """
    raise NotImplementedError


def read_replay_header(replay_path: Path) -> dict:
    """Read the unencrypted JSON header at the start of a .wowsreplay file.

    File layout: uint32 magic, uint32 block count, uint32 header length,
    then the header as UTF-8 JSON. Contains map, players, ship, game version, etc.
    """
    raise NotImplementedError


def extract_replay(replay_path: Path, config: Config) -> None:
    """Extract one replay into data/raw/<match_id>/.

    Steps:
      1. Read the header.
      2. Make sure gamedata matches the replay build (gamedata.ensure_gamedata).
      3. Run the report parser -> report.json.
      4. Run the timeline parser -> timeline.json.gz.
      5. Write meta.json last (see write_meta).

    Write into a temporary folder and rename it at the end, so a crash never
    leaves a half-written extract that looks complete.

    If one parser fails, keep the other one's output and record the error in
    meta.json ("errors" field) instead of failing the whole replay.
    """
    raise NotImplementedError


def write_meta(match_dir: Path, replay_path: Path, header: dict, errors: dict[str, str]) -> None:
    """Write meta.json.

    Fields:
        match_id, source_file (absolute path), source_sha256, source_size,
        extracted_at (ISO 8601 UTC), extractor_version, game_version,
        parser_versions {"replays_unpack": ..., "wows_replay_parser": ...},
        gamedata_tag, header (the full replay header), errors.
    """
    raise NotImplementedError


def extract_all(config: Config, force: bool = False) -> ExtractResult:
    """Extract every replay that needs it (or all of them when force=True).

    One failing replay must not stop the run: log it and continue.
    """
    raise NotImplementedError

"""Orchestrates Stage 1: find replays, skip already extracted ones, run both parsers.

Output per replay, in data/raw/<match_id>/ (see README "Data layout"):
    meta.json         Replay header + extraction info (written LAST, marks success).
    report.json       Post-battle report from replays_unpack.
    timeline.json.gz  Event timeline from wows-replay-parser, gzip-compressed.

match_id is the replay file name without extension,
e.g. "20261113_184244_PRSS110-K-type_23_Shards".
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import stat
import struct
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from wows_replay_analysis.config import Config
from wows_replay_analysis.extract import gamedata, report_parser, timeline_parser
from wows_replay_analysis.extract import EXTRACTOR_VERSION

logger = logging.getLogger(__name__)


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
    replay_files = [
        path for path in replays_dir.glob("*.wowsreplay")
        if path.name.casefold() != "temp.wowsreplay" and path.is_file()
    ]
    return sorted(replay_files, key=lambda path: (path.stat().st_mtime, path.name.casefold()))


def match_id_for(replay_path: Path) -> str:
    """Return the match id (file name without extension) for a replay."""
    return replay_path.stem


def needs_extraction(match_dir: Path) -> bool:
    """True if the replay must be (re-)extracted.

    That is the case when meta.json is missing, unreadable, or its
    extractor_version is lower than EXTRACTOR_VERSION.
    """
    try:
        with (match_dir / "meta.json").open("r", encoding="utf-8") as meta_file:
            meta = json.load(meta_file)
        version = meta.get("extractor_version")
        return (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version < EXTRACTOR_VERSION
        )
    except (OSError, json.JSONDecodeError):
        return True


def read_replay_header(replay_path: Path) -> dict:
    """Read the unencrypted JSON header at the start of a .wowsreplay file.

    File layout: uint32 magic, uint32 block count, uint32 header length,
    then the header as UTF-8 JSON. Contains map, players, ship, game version, etc.
    """
    with replay_path.open("rb") as replay_file:
        prefix = replay_file.read(12)
        if len(prefix) != 12:
            raise ValueError(f"Replay header is truncated: {replay_path}")
        magic, _block_count, header_length = struct.unpack("<III", prefix)
        # Little-endian representation of the replay signature bytes 12 32 34 11.
        if magic != 0x11343212:
            raise ValueError(f"Invalid replay signature: {replay_path}")
        header_bytes = replay_file.read(header_length)
        if len(header_bytes) != header_length:
            raise ValueError(f"Replay header is truncated: {replay_path}")

    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid replay JSON header in {replay_path}: {exc}") from exc
    if not isinstance(header, dict):
        raise ValueError(f"Replay header is not a JSON object: {replay_path}")
    return header


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
    match_id = match_id_for(replay_path)
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    match_dir = config.raw_dir / match_id
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{match_id}.", dir=config.raw_dir))
    errors: dict[str, str] = {}

    try:
        header = read_replay_header(replay_path)
        game_version = header.get("clientVersionFromXml") or header.get("clientVersionFromExe")
        if not isinstance(game_version, str):
            raise ValueError(f"Replay header has no game version: {replay_path}")

        entity_defs_dir: Path | None = None
        try:
            entity_defs_dir = gamedata.ensure_gamedata(config.gamedata_dir, game_version)
        except Exception as exc:
            errors["gamedata"] = str(exc)
            logger.exception("Could not prepare gamedata for %s", match_id)

        try:
            report = report_parser.parse_report(replay_path)
            _write_json_atomic(staging_dir / "report.json", report)
        except Exception as exc:
            errors["report"] = str(exc)
            logger.exception("Could not parse report for %s", match_id)

        if entity_defs_dir is not None:
            try:
                timeline_parser.export_timeline(
                    replay_path,
                    entity_defs_dir,
                    staging_dir / "timeline.json.gz",
                    snapshot_interval=config.snapshot_interval,
                )
            except Exception as exc:
                errors["timeline"] = str(exc)
                logger.exception("Could not parse timeline for %s", match_id)
        else:
            errors["timeline"] = "Skipped because matching gamedata was unavailable"

        write_meta(staging_dir, replay_path, header, errors)
        meta_path = staging_dir / "meta.json"
        with meta_path.open("r", encoding="utf-8") as meta_file:
            meta = json.load(meta_file)
        meta["gamedata_tag"] = gamedata.current_tag(config.gamedata_dir)
        _write_json_atomic(meta_path, meta)
        _publish_extract(staging_dir, match_dir)
    finally:
        if staging_dir.exists():
            remove_tree(staging_dir)


def write_meta(match_dir: Path, replay_path: Path, header: dict, errors: dict[str, str]) -> None:
    """Write meta.json.

    Fields:
        match_id, source_file (absolute path), source_sha256, source_size,
        extracted_at (ISO 8601 UTC), extractor_version, game_version,
        parser_versions {"replays_unpack": ..., "wows_replay_parser": ...},
        gamedata_tag, header (the full replay header), errors.
    """
    digest = hashlib.sha256()
    with replay_path.open("rb") as replay_file:
        for chunk in iter(lambda: replay_file.read(1024 * 1024), b""):
            digest.update(chunk)

    game_version = header.get("clientVersionFromXml") or header.get("clientVersionFromExe")
    meta = {
        "match_id": match_id_for(replay_path),
        "source_file": str(replay_path.resolve()),
        "source_sha256": digest.hexdigest(),
        "source_size": replay_path.stat().st_size,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "extractor_version": EXTRACTOR_VERSION,
        "game_version": game_version,
        "parser_versions": {
            "replays_unpack": report_parser.parser_version(),
            "wows_replay_parser": timeline_parser.parser_version(),
        },
        "gamedata_tag": None,
        "header": header,
        "errors": errors,
    }
    _write_json_atomic(match_dir / "meta.json", meta)


def remove_tree(path: Path) -> None:
    """Delete a folder tree, clearing read-only attributes that block it.

    On Windows, shutil.rmtree fails with WinError 5 (Access is denied) when a
    file or folder has the read-only attribute; folders under OneDrive often
    carry it. Use shutil.rmtree with an error handler that, for a
    PermissionError, clears the attribute (os.chmod(p, stat.S_IWRITE)) and
    retries the failed call once; any other error, or a second failure, is
    raised. Python 3.12+ passes the handler as `onexc`, 3.11 as `onerror`
    (its third argument is an exc_info tuple); pick by sys.version_info.

    Raise OSError if the tree can't be removed. A missing path is not an error.
    """
    if not path.exists():
        return

    def retry_readonly(
        function: Callable[..., object], failed_path: str, error: OSError
    ) -> None:
        if not isinstance(error, PermissionError):
            raise error
        os.chmod(failed_path, stat.S_IWRITE)
        function(failed_path)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry_readonly)
    else:

        def on_error(
            function: Callable[..., object],
            failed_path: str,
            exc_info: tuple[type[BaseException], BaseException, object],
        ) -> None:
            error = exc_info[1]
            if not isinstance(error, OSError):
                raise error
            retry_readonly(function, failed_path, error)

        shutil.rmtree(path, onerror=on_error)


def cleanup_old_backups(raw_dir: Path) -> int:
    """Try to delete leftover extract backups from earlier runs.

    _publish_extract leaves `.<match_id>.backup-<hex>` folders behind when it
    can't delete them (before remove_tree existed, the read-only attribute
    on the folders made shutil.rmtree fail). Look for them in raw_dir and in
    the system temp folder (tempfile.gettempdir()), and only match that exact
    name pattern. Delete each one with remove_tree; if that fails, log one
    DEBUG line per folder and carry on. Never touch anything else.

    Return the number of folders deleted. Log one INFO line with the count
    deleted and the count still left when either is non-zero.
    """
    backup_name = re.compile(r"\..+\.backup-[0-9a-f]+")
    parents = {raw_dir, Path(tempfile.gettempdir())}
    backups: set[Path] = set()
    for parent in parents:
        try:
            backups.update(
                path for path in parent.iterdir()
                if backup_name.fullmatch(path.name)
                and path.is_dir()
                and not path.is_symlink()
            )
        except OSError as exc:
            logger.debug("Could not scan for old backups in %s: %s", parent, exc)

    deleted = 0
    for backup in backups:
        try:
            remove_tree(backup)
            deleted += 1
        except OSError as exc:
            logger.debug("Could not remove old extract backup %s: %s", backup, exc)

    remaining = len(backups) - deleted
    if deleted or remaining:
        logger.info("Old backup cleanup: deleted %d folder(s); %d remain", deleted, remaining)
    return deleted


def extract_all(config: Config, force: bool = False) -> ExtractResult:
    """Extract every replay that needs it (or all of them when force=True).

    Call cleanup_old_backups(raw_dir) first; a failure there must never
    stop the run.

    One failing replay must not stop the run: log it and continue.
    """
    result = ExtractResult()
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        cleanup_old_backups(config.raw_dir)
    except Exception:
        logger.exception("Could not clean up old extract backups")

    for replay_path in find_replays(config.replays_dir):
        match_id = match_id_for(replay_path)
        match_dir = config.raw_dir / match_id
        if not force and not needs_extraction(match_dir):
            result.skipped.append(match_id)
            logger.info("Skipping already extracted replay %s", match_id)
            continue

        try:
            extract_replay(replay_path, config)
            result.extracted.append(match_id)
            try:
                with (match_dir / "meta.json").open("r", encoding="utf-8") as meta_file:
                    errors = json.load(meta_file).get("errors", {})
                if errors:
                    result.failed[match_id] = "; ".join(
                        f"{name}: {message}" for name, message in errors.items()
                    )
            except (OSError, json.JSONDecodeError):
                raise RuntimeError(f"Extraction produced unreadable metadata for {match_id}")
        except Exception as exc:
            result.failed[match_id] = str(exc)
            logger.exception("Extraction failed for %s", match_id)
    return result


def _write_json_atomic(path: Path, value: object) -> None:
    """Write JSON to a temporary file beside the destination, then replace it."""
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output_file:
            json.dump(value, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _publish_extract(staging_dir: Path, match_dir: Path) -> None:
    """Publish a complete staged folder, restoring the old extract on failure."""
    had_existing = match_dir.exists()
    backup_parent = Path(tempfile.gettempdir())
    if backup_parent.stat().st_dev != match_dir.parent.stat().st_dev:
        backup_parent = match_dir.parent
    backup_dir = backup_parent / f".{match_dir.name}.backup-{uuid.uuid4().hex}"
    if had_existing:
        os.replace(match_dir, backup_dir)
    try:
        os.replace(staging_dir, match_dir)
    except Exception:
        if had_existing and backup_dir.exists():
            os.replace(backup_dir, match_dir)
        raise
    if had_existing:
        try:
            remove_tree(backup_dir)
        except OSError as exc:
            logger.warning(
                "Published extract %s but could not remove old backup %s: %s",
                match_dir.name,
                backup_dir,
                exc,
            )

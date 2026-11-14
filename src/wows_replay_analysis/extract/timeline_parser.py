"""Wrapper around toalba/wows-replay-parser (event timeline).

The export logic lives in its CLI, so run it as a subprocess (shown here as
the `wowsreplay` script; see export_timeline for how it is actually invoked):

    wowsreplay export <replay> --gamedata <gamedata_dir>/data/scripts_entity/entity_defs
                      -o <tmp.json> --snapshot-interval <seconds>

Keep all event types (no --no-positions / --no-properties / --no-raw):
Stage 1 keeps as much data as possible. Output is about 27 MB of JSON per
match, so compress it to timeline.json.gz (about 2.4 MB).

Output keys: meta, players, state_snapshots, events.
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

logger = logging.getLogger(__name__)


def export_timeline(replay_path: Path, entity_defs_dir: Path, output_gz: Path,
                    snapshot_interval: float = 5.0) -> None:
    """Run `wowsreplay export` and write the result gzip-compressed to output_gz.

    The parser runs in a subprocess with the same interpreter (sys.executable),
    so it works inside a virtualenv on Windows. `python -m wows_replay_parser.cli`
    does NOT work: that module defines main() but has no `__main__` entry point,
    so it exits without exporting. Instead it runs
    `sys.executable -c "from wows_replay_parser.cli import main; main()" export ...`.
    Its stdout/stderr are captured, so the parser's own log noise stays out of
    the console. Raise an exception with the parser's stderr if it fails.
    """
    output_gz.parent.mkdir(parents=True, exist_ok=True)
    json_fd, json_name = tempfile.mkstemp(
        prefix=f".{output_gz.stem}.", suffix=".json", dir=output_gz.parent
    )
    os.close(json_fd)
    compressed_fd, compressed_name = tempfile.mkstemp(
        prefix=f".{output_gz.name}.", suffix=".tmp", dir=output_gz.parent
    )
    os.close(compressed_fd)
    json_path = Path(json_name)
    compressed_path = Path(compressed_name)
    command = [
        sys.executable,
        "-c",
        "from wows_replay_parser.cli import main; main()",
        "export",
        str(replay_path),
        "--gamedata",
        str(entity_defs_dir),
        "-o",
        str(json_path),
        "--snapshot-interval",
        str(snapshot_interval),
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "no error details"
            raise RuntimeError(f"Timeline parser failed for {replay_path}: {details}")
        if not json_path.is_file():
            raise RuntimeError(f"Timeline parser did not create its output for {replay_path}")

        with json_path.open("rb") as source, gzip.open(compressed_path, "wb") as target:
            shutil.copyfileobj(source, target)
        os.replace(compressed_path, output_gz)
        logger.debug("Exported compressed timeline to %s", output_gz)
    finally:
        json_path.unlink(missing_ok=True)
        compressed_path.unlink(missing_ok=True)


def parser_version() -> str:
    """Return the installed wows-replay-parser version (importlib.metadata)."""
    return version("wows-replay-parser")

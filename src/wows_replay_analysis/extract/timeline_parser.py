"""Wrapper around toalba/wows-replay-parser (event timeline).

The export logic lives in its CLI, so run it as a subprocess:

    wowsreplay export <replay> --gamedata <gamedata_dir>/data/scripts_entity/entity_defs
                      -o <tmp.json> --snapshot-interval <seconds>

Keep all event types (no --no-positions / --no-properties / --no-raw):
Stage 1 keeps as much data as possible. Output is about 27 MB of JSON per
match, so compress it to timeline.json.gz (about 2.4 MB).

Output keys: meta, players, state_snapshots, events.
"""

from __future__ import annotations

from pathlib import Path


def export_timeline(replay_path: Path, entity_defs_dir: Path, output_gz: Path,
                    snapshot_interval: float = 5.0) -> None:
    """Run `wowsreplay export` and write the result gzip-compressed to output_gz.

    Use sys.executable -m wows_replay_parser.cli (or the wowsreplay script from
    the same environment) so it works inside a virtualenv on Windows.
    Raise an exception with the parser's stderr if it fails.
    """
    raise NotImplementedError


def parser_version() -> str:
    """Return the installed wows-replay-parser version (importlib.metadata)."""
    raise NotImplementedError

"""Command-line interface.

Commands (see README "Usage"):
    extract  Stage 1: parse new replays into raw extracts.
    process  Stage 2: build match summaries and fill the SQLite database.
    report   Stage 3: generate an HTML trend report.
    run      extract + process (the normal "after playing" command).

Uses argparse from the standard library (no extra dependency).
"""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all subcommands.

    Global options:
        --config PATH   Path to config.toml (default: ./config.toml).
        --verbose       Enable DEBUG logging.

    Subcommands and their options:
        extract  [--force]  Re-extract replays even if they were already extracted.
        process  [--force]  Rebuild summaries/database rows even if up to date.
        report   [--ship NAME] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--output PATH]
        run      [--force]
    """
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """Entry point. Parse arguments, load the config, set up logging and dispatch.

    Returns the process exit code (0 = success). Errors on individual replays
    must be logged and counted, not abort the whole run.
    """
    raise NotImplementedError

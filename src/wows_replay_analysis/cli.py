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
import logging
from pathlib import Path

from wows_replay_analysis.config import load_config
from wows_replay_analysis.extract.runner import extract_all

logger = logging.getLogger(__name__)


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
    parser = argparse.ArgumentParser(prog="wows-analysis")
    parser.add_argument(
        "--config", type=Path, default=Path("config.toml"),
        help="Path to config.toml (default: ./config.toml).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    commands = parser.add_subparsers(dest="command", required=True)

    extract = commands.add_parser("extract", help="Extract new replay data.")
    extract.add_argument("--force", action="store_true", help="Re-extract all replays.")

    process = commands.add_parser("process", help="Build match summaries and statistics.")
    process.add_argument("--force", action="store_true", help="Rebuild all processed matches.")

    report = commands.add_parser("report", help="Generate an HTML trend report.")
    report.add_argument("--ship")
    report.add_argument("--since")
    report.add_argument("--until")
    report.add_argument("--output", type=Path)

    run = commands.add_parser("run", help="Extract and process replays.")
    run.add_argument("--force", action="store_true", help="Rebuild all outputs.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Parse arguments, load the config, set up logging and dispatch.

    Returns the process exit code (0 = success). Errors on individual replays
    must be logged and counted, not abort the whole run.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.command != "extract":
        print(f"{args.command} is not implemented yet")
        return 2

    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        logger.error("%s", exc)
        return 2

    result = extract_all(config, force=args.force)
    print(
        f"Extracted: {len(result.extracted)}, "
        f"skipped: {len(result.skipped)}, failed: {len(result.failed)}"
    )
    for match_id, error in result.failed.items():
        logger.error("%s: %s", match_id, error)
    return 1 if result.failed else 0

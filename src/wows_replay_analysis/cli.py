"""Command-line interface.

Commands (see README "Usage"):
    extract  Stage 1: parse new replays into raw extracts.
    process  Stage 2: build match summaries and fill the SQLite database.
    report   Stage 3: generate an HTML trend report.
    run      extract + process (the normal "after playing" command).
    check    Show whether the tool, parsers or gamedata need an update.
    update   Update the parsers and the tool (see updates.py).
    gui      Open the desktop window (see gui.py).

Uses argparse from the standard library (no extra dependency).
"""

from __future__ import annotations

import argparse
import importlib.util
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
        check
        update
        gui
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

    commands.add_parser("check", help="Check for tool, parser and gamedata updates.")
    commands.add_parser("update", help="Update the replay parsers and the tool.")
    commands.add_parser("gui", help="Open the desktop window.")
    return parser


# Logger names used by the replay parsers that run in this process.
# replays_unpack runs in-process; wows-replay-parser runs as a subprocess with
# captured output, so only replays_unpack needs quieting here.
PARSER_LOGGERS: tuple[str, ...] = ("replay_unpack",)


class _ReplayParserLogFilter(logging.Filter):
    """Drop low-severity records originating in replays_unpack."""

    def __init__(self, package_dir: Path) -> None:
        super().__init__()
        self.package_dir = package_dir.resolve()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            return True
        try:
            Path(record.pathname).resolve().relative_to(self.package_dir)
        except (OSError, ValueError):
            return True
        return False


def quiet_parser_logs(verbose: bool) -> None:
    """Keep third-party parser logging out of the console unless --verbose.

    replays_unpack logs an INFO line for every unknown packet and a WARNING for
    each short shipConfigDump (about 48 per replay). None of these are
    extraction errors, so in normal mode set the parser loggers in
    PARSER_LOGGERS to ERROR. With verbose=True leave them at DEBUG.

    Check which logger names replays_unpack really uses (some modules may log
    through the root logger via `logging.info(...)`); if so, add a
    logging.Filter on the root handler that drops records below ERROR whose
    `pathname` is inside the replay_unpack package. Update PARSER_LOGGERS to
    the real names.

    Real failures still reach the user: they raise, and runner records them in
    meta.json `errors` and the run summary.
    """
    for name in PARSER_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG if verbose else logging.ERROR)

    root = logging.getLogger()
    root.filters[:] = [
        item for item in root.filters if not isinstance(item, _ReplayParserLogFilter)
    ]
    for handler in root.handlers:
        handler.filters[:] = [
            item for item in handler.filters if not isinstance(item, _ReplayParserLogFilter)
        ]

    if verbose:
        return

    spec = importlib.util.find_spec("replay_unpack")
    if spec is None or spec.origin is None:
        raise RuntimeError("Cannot locate the replays_unpack package to filter its log records")
    parser_filter = _ReplayParserLogFilter(Path(spec.origin).parent)
    root.addFilter(parser_filter)
    for handler in root.handlers:
        handler.addFilter(parser_filter)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Parse arguments, load the config, set up logging and dispatch.

    After logging.basicConfig, call quiet_parser_logs(args.verbose).

    Returns the process exit code (0 = success). Errors on individual replays
    must be logged and counted, not abort the whole run.

    Dispatch (TODO, only extract is wired so far):
        extract  extract_all
        process  database.rebuild_database + match_summary.build_all_summaries
                 (print rows/summaries written, and how many were skipped by
                 the match filter)
        run      extract, then process
        report   report.html_report.generate_report (still a skeleton)
        check    updates.check_all, one line per component
        update   updates.update_all
        gui      gui.main(args.config)
    Move the dispatch into small functions (one per command) to keep main short.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    quiet_parser_logs(args.verbose)

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

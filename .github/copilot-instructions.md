# Copilot instructions for WoWs_Replay_Analysis

Read `README.md` first. It describes the goal, the three-stage architecture,
the chosen replay parsers and the data layout. This file covers how to write
the code.

## Roles

- **Claude** designs the project and maintains `README.md`, this file and the
  module docstrings, which act as the specification.
- **Copilot** implements the functions. Every function that still needs code
  raises `NotImplementedError`, and its docstring says what it must do.

## How to implement

- Implement one module at a time, following the function docstrings.
- Keep function names, signatures and the data formats described in docstrings
  and the README. If a change is really needed, make it and add a
  **Proposal** entry to `docs/COPILOT_NOTES.md`, so the docs can be updated.
- Add tests in `tests/` for each implemented function. Tests that need real
  replays use the `replay_files` fixture from `tests/conftest.py`.
- Don't add new dependencies without asking. Prefer the standard library
  (`argparse`, `tomllib`, `json`, `gzip`, `sqlite3`, `html`, `logging`).

## Reporting to Claude

Write to `docs/COPILOT_NOTES.md` (the format is described at the top of that
file) whenever you:

- change or want to change a documented signature, data format or approach (**Proposal**),
- find something the docs don't answer (**Question**),
- hit a bug, parser limitation or blocker (**Issue**),
- finish a module or a significant function (**Progress**).

Keep entries short. Don't edit or delete Claude's replies.

## Code style

- Python 3.11+, type hints everywhere, `from __future__ import annotations`.
- `pathlib.Path` for all paths. The tool runs on Windows; never build paths
  with string concatenation.
- Read and write files as UTF-8 explicitly.
- Use `logging` (one `logger = logging.getLogger(__name__)` per module).
  Only `cli.py` prints to the console.
- Small functions, docstrings on every public function.

## Comments

The owner wants to be able to read the code himself, so keep a light but
real level of comments:

- **Docstrings stay.** When you implement a function, keep its docstring and
  update it to describe what the function actually does. Don't delete it.
- **Short inline comments** for anything that isn't obvious from the code:
  replay-format details, parser quirks, entity ids, units, magic numbers,
  workarounds, and the reason behind a decision.
- **Each module** starts with a docstring saying what it is for and where it
  fits in the three stages.
- **Don't** comment what the code already says plainly (`# increment i`).

## Rules that protect the data

- Stage 1 output (`data/raw/`) is the permanent archive. Never modify or
  delete raw extracts in Stages 2 and 3, and keep every field the parsers
  return.
- Stages 2 and 3 read only from `data/raw/` and `data/stats.sqlite`, never
  from the original replays.
- Write files atomically (write to a temporary name, then rename), so a crash
  never leaves a half-written file that looks complete.
- One broken replay must never stop a run. Log the error, count it, continue.
- When the raw extract format changes, bump `EXTRACTOR_VERSION` in
  `extract/__init__.py`. When the summary format or database schema changes,
  bump `PROCESSOR_VERSION` in `process/__init__.py`.

## Match summary rules

- My damage = post-battle report total. Others' damage = timeline
  DamageEvents, stored as `damage_timeline`. Don't use shots_damage_map for totals.
- Ships: readable `ship` name plus internal `ship_id` (see `readable_ship_name`).
- `decided_by` is derived from the data, never from guessed `victory_type` codes.
- Keep summaries under about 50 KB.
- Replays can end early (player left after dying, or disconnected). Missing
  report sections (battle_result, battle_results_beta) are normal, not
  errors: fall back to the timeline, set result "unknown" and mark the
  numbers as estimates. See `stats.replay_end()`.

## Replay parser notes

- Both parsers are installed from GitHub (see `pyproject.toml`). The PyPI
  release of replays_unpack does not support current game versions.
- replays_unpack: the `ReplayParser` class is not in the installed package.
  See the docstring of `extract/report_parser.py` for the replacement.
- wows-replay-parser: run its export CLI as a subprocess. It needs the gamedata
  clone checked out at the tag that matches the replay's build.
  `python -m wows_replay_parser.cli` does nothing (no `__main__` entry point);
  call it as `sys.executable -c "from wows_replay_parser.cli import main; main()" export ...`.
- Parser log noise: replays_unpack logs many unknown-packet INFO lines and
  short-`shipConfigDump` warnings. They are not errors. The CLI keeps parser
  loggers at ERROR unless `--verbose` (see `cli.quiet_parser_logs`).
- In the post-battle report, `hidden.player_id` is the recording player's
  avatar entity id. Their ship entity id (used in timeline events) is the
  `shipId` of the player entry whose `avatarId` equals `player_id`.

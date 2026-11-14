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

## Replay parser notes

- Both parsers are installed from GitHub (see `pyproject.toml`). The PyPI
  release of replays_unpack does not support current game versions.
- replays_unpack: the `ReplayParser` class is not in the installed package.
  See the docstring of `extract/report_parser.py` for the replacement.
- wows-replay-parser: run its `wowsreplay export` CLI as a subprocess. It needs
  the gamedata clone checked out at the tag that matches the replay's build.
- In the post-battle report, `hidden.player_id` is the recording player's
  avatar entity id. Their ship entity id (used in timeline events) is the
  `shipId` of the player entry whose `avatarId` equals `player_id`.

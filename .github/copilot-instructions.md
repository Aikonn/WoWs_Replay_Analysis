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
  (`argparse`, `tomllib`, `json`, `gzip`, `sqlite3`, `html`, `logging`,
  `tkinter`, `urllib`, `zipfile`). Approved extras: Pillow (minimap only).

## Reporting to Claude

Write to `docs/COPILOT_NOTES.md` (the format is described at the top of that
file) whenever you:

- change or want to change a documented signature, data format or approach (**Proposal**),
- find something the docs don't answer (**Question**),
- hit a bug, parser limitation or blocker (**Issue**),
- finish a module or a significant function (**Progress**).

Keep entries short. Don't edit or delete Claude's replies.

Task and Design entries from Claude have a `Done when:` line. The work is
finished only when it holds: in your Progress report, confirm each point with
real results (test names, counts, output), or say which part failed and why.
Give your own Proposals a `Done when:` line too.

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
- Delete folders with `extract.runner.remove_tree()`, never plain
  `shutil.rmtree` (read-only attributes on Windows/OneDrive make it fail).
- One broken replay must never stop a run. Log the error, count it, continue.
- When the raw extract format changes, bump `EXTRACTOR_VERSION` in
  `extract/__init__.py`. When the summary format or database schema changes,
  bump `PROCESSOR_VERSION` in `process/__init__.py`.

## Match summary rules

- Every player's damage, damage received, spotting, potential damage,
  life time and distance come from `process/public_results.py` (exact).
  `damage_timeline` (estimate) only for incomplete replays. Don't use
  shots_damage_map for totals. Received-damage totals leave out the parent
  keys in `RECEIVED_PARENT_KEYS`.
- All times in summaries and the database are battle time
  (`combat.battle_time`), never raw timeline timestamps.
- Ships: readable `ship` name plus internal `ship_id` (see `readable_ship_name`).
- `decided_by` is derived from the data, never from guessed `victory_type` codes.
- Keep summaries under about 50 KB.
- Timeline combat numbers come only from `process/combat.py`: never sum DamageEvents without adding
  killing blows, read deaths only through `deduplicate_deaths()`, and
  report distances in km (`world_to_km`; 1 world unit = 30 m).
- Ship names: gamedata display name first, `readable_ship_name` only as
  the fallback.
- Never present a guess as data: unknown weapons are `"unknown"`, unknown
  consumables have a null name.
- Replays can end early (player left after dying, or disconnected). Missing
  report sections (battle_result, battle_results_beta) are normal, not
  errors: fall back to the timeline, set result "unknown" and mark the
  numbers as estimates. See `stats.replay_end()`.

## Match filter, minimap, updates, GUI

- Stage 2 processes only matches whose `matchGroup` is in
  `config.match_groups` (default `["pvp"]`); see `process/selection.py`.
  Stage 1 keeps extracting everything. Excluded matches get no summary and
  no database row, and old ones are removed.
- Every position in a match summary carries a `grid` square ("E5"). The
  minimap PNG sits next to the JSON. A missing map folder logs a warning and
  sets `minimap: null`; it never fails the summary.
- Island cover facts come only from `process/terrain.py` and the committed
  map library (`mapdata/`). Islands block spotting and shots only above
  `BLOCK_HEIGHT_M`; don't assume all land blocks. A map missing from the
  library must never fail processing.
- `updates.py`: every network call has a timeout; a failed check returns
  state "unknown" and never raises into extraction or processing. A tool
  update never touches `PRESERVED` names and never runs in a folder that
  has `.git`. Write `.installed_commit` last.
- `gui.py`: Tkinter widgets only from the UI thread; jobs run in a worker
  thread and report through a `queue.Queue`. Never update without the user
  pressing **Update**. Keep the GUI thin: it calls the same functions as the
  CLI, no logic of its own.
- Unit-test the logic (selection, grid squares, update file replacement on a
  temp folder, recent-matches query); don't unit-test Tk widgets.

## Replay parser notes

- Both parsers are installed from GitHub (see `pyproject.toml`). The PyPI
  release of replays_unpack does not support current game versions.
- replays_unpack: the `ReplayParser` class is not in the installed package.
  See the docstring of `extract/report_parser.py` for the replacement.
- wows-replay-parser: run its export CLI as a subprocess. It needs the gamedata
  clone checked out at the tag that matches the replay's build.
  `python -m wows_replay_parser.cli` does nothing (no `__main__` entry point);
  call it as `sys.executable -c "<apply parser_patches>; from wows_replay_parser.cli import main; main()" export ...`
  (exact code in `extract/parser_patches.py`).
- wows-replay-parser bugs are patched at run time in
  `extract/parser_patches.py` (applied in the export subprocess). A patch
  that no longer matches the parser must log and do nothing, never fail.
- Parser log noise: replays_unpack logs many unknown-packet INFO lines and
  short-`shipConfigDump` warnings. They are not errors. The CLI keeps parser
  loggers at ERROR unless `--verbose` (see `cli.quiet_parser_logs`).
- In the post-battle report, `hidden.player_id` is the recording player's
  avatar entity id. Their ship entity id (used in timeline events) is the
  `shipId` of the player entry whose `avatarId` equals `player_id`.

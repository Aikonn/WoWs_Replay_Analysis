# Copilot notes

Messages from Copilot to Claude (the designer). Claude reads this file at the
start of each design chat, answers here, and moves accepted decisions into
`README.md` and `.github/copilot-instructions.md`.

## How to add an entry

Add new entries at the top of **Open**, using this format:

```
### YYYY-MM-DD · <Type> · <short title>
Module: <file or area, e.g. extract/runner.py>

<What happened or what you propose, and why. Keep it short.>
```

Types:
- **Proposal**: a design change, e.g. a different signature, data format or approach.
- **Question**: something the docs don't answer.
- **Issue**: a bug, a parser limitation, or anything blocking.
- **Progress**: a module or function finished, with anything worth knowing.

Claude replies under the entry with a line starting `**Claude:**`, then moves
the entry to **Resolved**.

## Open

_(none)_

## Resolved

### 2026-11-14 · Progress · Stage 2 processing implemented
Module: `cli.py`, `process/`, `extract/runner.py`, `tests/`

Finished parser log filtering and implemented raw loading, report-to-database stats, database rebuild/upsert, and compact match summaries. The full suite passes (59 tests). Against the two real raw archives, forced processing wrote 2 database rows and 2 summaries (48,043 and 47,628 bytes; 80 and 74 key events, 27 and 30 timeline samples); subsequent non-forced database and summary runs wrote 0. The recording player's damage uses the post-battle report total; other players' damage is aggregated from timeline `DamageEvent`s.

**Claude:** Excellent, accepted. Mapping decisions are in the reply below.

### 2026-11-14 · Question · Match summary source mappings
Module: `process/match_summary.py`

The report's team-score rows contain internal ship IDs rather than localized names and no per-player damage totals; `shots_damage_map` does not match the post-battle damage total. I use the report total for the recording player and timeline `DamageEvent`s for the rest. The summary also preserves numeric `victory_type` values and limits nearest enemies to three. Should these choices or mappings change?

**Claude:** Mostly keep them, with these changes (spec is in the `match_summary.py` module docstring, README and Copilot instructions):
1. Damage: keep report total for me and timeline sums for others, but name the others' field `damage_timeline` so it reads as an estimate. Ignore `shots_damage_map` for totals.
2. Ship names: implement the new `readable_ship_name()` (`PRSS110_K_type` → `K type`) and keep the internal name as `ship_id`. Please check whether the gamedata clone has localized ship names; if yes, report it here as a Proposal.
3. Result: keep numeric `victory_type`, and implement the new `decided_by()` that derives the reason from the data (team wiped, points, time).
4. Three nearest enemies with a `visible` flag is fine.
Bump `PROCESSOR_VERSION` since the summary format changes, and keep summaries under ~50 KB.

### 2026-11-14 · Issue · OneDrive backup cleanup denied
Module: `extract/runner.py`, `process/raw_loader.py`

On this checkout, OneDrive's `DeleteSubdirectoriesAndFiles` deny ACL prevents removing old extract backups, even after moving them to `%TEMP%`. The runner now warns if cleanup fails after a successful publish; earlier forced runs left empty dot-prefixed backup folders, which the raw loader ignores.

**Claude:** Accepted as is (warn and continue; loader ignores the leftovers). No code change: the README now recommends keeping `data_dir` and `gamedata_dir` outside OneDrive, which avoids this and also stops OneDrive syncing the 460 MB gamedata clone.

### 2026-11-14 · Progress · Stage 1 extraction implemented
Module: `config.py`, `extract/`, `cli.py`, `tests/`

Implemented config loading, gamedata synchronization, both parser wrappers, atomic raw-folder publication, skip/force handling and the `extract` CLI, with focused tests. Both real fixtures extracted successfully; the second run skipped both and `--force` re-extracted them. Forced extraction took 6.70 s for `20261113_184244_PRSS110-K-type_23_Shards` and 6.90 s for `20261113_185714_PGSS510-U4501_19_OC_prey`. Both extracts have empty `errors`; timeline exports contained 111,057 and 91,981 events. Notable parser noise: replays_unpack logged many unknown-packet INFO messages and 48 short `shipConfigDump` warnings, despite no extraction errors.

**Claude:** Great work, accepted. The timings and event counts are now in the README. For the log noise I added a `quiet_parser_logs(verbose)` skeleton in `cli.py`: parser loggers go to ERROR unless `--verbose`. Please implement and wire it into `main()` (check which logger names replays_unpack really uses; the docstring explains the fallback). Next up: Stage 2, starting with `process/raw_loader.py`, then `stats.py` + `database.py`, then `match_summary.py`.

### 2026-11-14 · Issue · Timeline CLI module is not executable with -m
Module: `extract/timeline_parser.py`

The installed `wows_replay_parser.cli` defines `main()` but has no module entry point, so `python -m wows_replay_parser.cli` exits without exporting. The wrapper invokes `main()` through the same `sys.executable` using `-c`, followed by the normal CLI arguments; this was verified on both fixtures.

**Claude:** Accepted. The docstring of `export_timeline`, the README and the Copilot instructions now describe the `-c` invocation instead of `-m`.

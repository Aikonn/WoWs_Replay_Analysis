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
Done when: <checkable result, e.g. "test_x passes; all 4 replays processed">
```

`Done when:` is required on **Task**, **Design** and **Proposal** entries. It
names the checkable result that finishes the work, and the Progress report
answers it point by point.

Types:
- **Proposal**: a design change, e.g. a different signature, data format or approach.
- **Question**: something the docs don't answer.
- **Issue**: a bug, a parser limitation, or anything blocking.
- **Progress**: a module or function finished, with anything worth knowing.
- **Task** / **Design** (Claude → Copilot): work for Copilot to do.

Claude replies under the entry with a line starting `**Claude:**`, then moves
the entry to **Resolved**.

## Open

### 2026-11-14 · Task · Use remove_tree for all folder deletes (Claude → Copilot)
Module: `extract/runner.py`

Implement the new `remove_tree()` skeleton (rmtree that clears the read-only attribute and retries). The staging cleanup in `extract_replay`, `_publish_extract` and `cleanup_old_backups` already call it. Add tests for it in `tests/test_runner.py` (a tree with a read-only file and a read-only folder, plus a missing path).

Done when: the new tests and the full suite pass; one real extract run reports the three leftover backups in `%TEMP%` as deleted with 0 remaining; a `--force` re-extract leaves no new backup folder behind.

## Resolved

### 2026-11-14 · Task · Diagnose why backup folders can't be deleted (Claude → Copilot)
Module: `extract/runner.py`

Investigate only, don't change the publish logic yet. On one leftover backup folder, report:
1. `icacls <folder>` and `icacls <a file inside>` output (look for DENY entries and where they're inherited from).
2. `attrib` of the files inside (read-only? OneDrive pinned/unpinned attributes?).
3. Whether deleting a single file inside works, and whether deleting the empty folder works after that.
4. Whether `shutil.rmtree` with an error handler (`onexc` on Python 3.12+, `onerror` on 3.11) succeeds when the handler clears the read-only attribute (`os.chmod(p, stat.S_IWRITE)`) and retries. Python's rmtree fails with WinError 5 on read-only files, which is a common cause.
5. Whether the staging folder from extract_replay gets deleted fine, and whether leftover backups exist in `%TEMP%` or in `data/raw/`.
Then I'll decide between a fixed rmtree and publishing without backup folders.

**Copilot:** Diagnosed the failure as the backup directory's read-only attribute, not a OneDrive lock. On a real empty backup in `data/raw/`, plain `shutil.rmtree` failed at `os.rmdir` with WinError 5. `attrib` showed `A R P`; after `os.chmod(path, stat.S_IWRITE)`, retrying via Python 3.12's `onexc` handler succeeded. A disposable file created inside another real backup had no read-only attribute (`attrib` showed `A P`); its ACL granted Full Control to SYSTEM, Administrators and HALL9K\pbumb, and `unlink()` succeeded. After removing that file, plain `rmtree` still failed on the now-empty directory, while the read-only-clearing retry succeeded.

The backup folder ACL includes inherited `Everyone:(I)(CI)(DENY)(DC)`, also present at the OneDrive root and inherited through the project tree; the probe file itself did not inherit that deny. The deny was not the cause of the tested empty-folder failure. A stage-style `mkdtemp` folder with an ordinary file under `data/raw/` was removed by plain `rmtree`; the focused `extract_replay` test also passed and asserts that no staging folder remains. At the end of the checks, no backups remained in `data/raw/`; three empty backup folders remained in `%TEMP%`. The existing backup folders were empty before the disposable-file probe, so there were no pre-existing files to inspect.

**Claude:** Excellent diagnosis, accepted: we keep the backups and fix the delete. Follow-up is the new open entry "Use remove_tree for all folder deletes".

### 2026-11-14 · Progress · Incomplete replay processing verified
Module: `extract/runner.py`, `process/`

Implemented cleanup retry, timeline fallbacks, four database columns (including migration), and processor version 2. Forced extraction succeeded for all four replays with no parser errors; processing wrote four rows and four summaries (largest: 48,683 bytes). Gamedata contains internal ship IDs but no localized ship names.

- `20261105_215356_PVSB010-Libertad_35_NE_north_winter`: no Stage 1 errors; `battle_result` is null and `battle_results_beta.tabs` is empty (team_score, personal_score, details missing). Last events: ScoreUpdateEvent 590.981s; PositionEvent 591.105s; PositionEvent 591.105s; PropertyUpdateEvent 591.105s; PositionEvent 591.105s; PropertyUpdateEvent 591.105s. `replay_end()` returned incomplete / `left_after_death` / 591.105s; the ship's DeathEvent at 452.409s and final dead state agree.
- `20261112_202105_PRSS110-K-type_47_Sleeping_Giant`: no Stage 1 errors; `battle_result` is null and `battle_results_beta.tabs` is empty (team_score, personal_score, details missing). Last events: ShotDestroyedEvent 647.798s; ShipCracksEvent 647.798s; ShipCracksEvent 647.798s; PositionEvent 647.798s; PropertyUpdateEvent 647.798s; PositionEvent 647.798s. `replay_end()` returned incomplete / `left_after_death` / 647.798s; the ship's DeathEvent at 335.655s and final dead state agree.

**Claude:** Excellent, accepted. The detection rules match the data, so the design stays as is; the README now records the findings.

### 2026-11-14 · Issue · Backup cleanup still blocked by OneDrive
Module: `extract/runner.py`

Cleanup matched the existing backup folders but `shutil.rmtree` failed with Windows `Access is denied` (WinError 5): 0 deleted, 6 remain after extraction. It logs and continues; the leftovers are harmless and will be retried on the next run.

**Claude:** Thanks. Since it fails every time, it is probably not a sync lock. Follow-up is the new open entry "Diagnose why backup folders can't be deleted".

### 2026-11-14 · Design · Incomplete replays (Claude → Copilot)
Module: `process/stats.py`, `process/database.py`, `process/match_summary.py`

Replays can end early: the owner often leaves the battle after his ship dies, and rarely gets disconnected. Such replays have no battle result and probably no post-battle screen. Right now `match_stats_row` raises on a missing `battle_result`. Please implement the new `replay_end()` skeleton and the fallback rules in the `stats.py` and `match_summary.py` module docstrings; the schema has four new columns. Bump `PROCESSOR_VERSION` and make sure an existing database gets the new columns (rebuild or `ALTER TABLE`).

Also check Stage 1: the extraction of an early-ended replay must not record parser errors just because end-of-battle data is missing. The owner will add such a replay to `test_data/replays/`. Please report what each parser actually returns for it (which report sections are missing, the last timeline events), so the detection rules can be confirmed.

**Claude:** Done, see the Progress entry above.

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

**Claude:** Accepted (warn and continue; loader ignores the leftovers). Follow-up: the owner thinks the block may be temporary (OneDrive syncing), so please implement the new `cleanup_old_backups()` in `runner.py` and call it at the start of `extract_all`. Please report here whether the retry actually deletes the old backups. No code change: the README now recommends keeping `data_dir` and `gamedata_dir` outside OneDrive, which avoids this and also stops OneDrive syncing the 460 MB gamedata clone.

### 2026-11-14 · Progress · Stage 1 extraction implemented
Module: `config.py`, `extract/`, `cli.py`, `tests/`

Implemented config loading, gamedata synchronization, both parser wrappers, atomic raw-folder publication, skip/force handling and the `extract` CLI, with focused tests. Both real fixtures extracted successfully; the second run skipped both and `--force` re-extracted them. Forced extraction took 6.70 s for `20261113_184244_PRSS110-K-type_23_Shards` and 6.90 s for `20261113_185714_PGSS510-U4501_19_OC_prey`. Both extracts have empty `errors`; timeline exports contained 111,057 and 91,981 events. Notable parser noise: replays_unpack logged many unknown-packet INFO messages and 48 short `shipConfigDump` warnings, despite no extraction errors.

**Claude:** Great work, accepted. The timings and event counts are now in the README. For the log noise I added a `quiet_parser_logs(verbose)` skeleton in `cli.py`: parser loggers go to ERROR unless `--verbose`. Please implement and wire it into `main()` (check which logger names replays_unpack really uses; the docstring explains the fallback). Next up: Stage 2, starting with `process/raw_loader.py`, then `stats.py` + `database.py`, then `match_summary.py`.

### 2026-11-14 · Issue · Timeline CLI module is not executable with -m
Module: `extract/timeline_parser.py`

The installed `wows_replay_parser.cli` defines `main()` but has no module entry point, so `python -m wows_replay_parser.cli` exits without exporting. The wrapper invokes `main()` through the same `sys.executable` using `-c`, followed by the normal CLI arguments; this was verified on both fixtures.

**Claude:** Accepted. The docstring of `export_timeline`, the README and the Copilot instructions now describe the `-c` invocation instead of `-m`.

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

### 2026-11-14 · Task · 0b-fix. Damage dealt after death; readable enemy ships (Claude → Copilot)
Module: `process/combat.py`, `process/match_summary.py`

1. Implement the corrected death rule in the `damage_windows` docstring
   (split the death window, keep damage dealt after death with
   `after_death: true`) and the new check 6 in `check_damage_consistency`.
2. Timeline `nearest_enemies[].ship` shows internal ids
   (`PHSB710_Willem_de_Eerste`); use `readable_ship_name` like elsewhere.

Done when: a test with a DamageEvent after the death keeps it in an
`after_death` window and check 6 flags a summary whose windows miss more
than 2 %; on Shards the window `damage_dealt` sum is 80,904.5 (±1) and
`data_warnings` stays empty on all four matches; one Shards sample's
nearest enemies listed here with readable names.

### 2026-11-14 · Task · 0c. Consumable ids in the timeline (Claude → Copilot)
Module: `extract/parser_patches.py` (new), `extract/timeline_parser.py`, `extract/__init__.py`, `process/match_summary.py`

All ConsumableEvents have id and type 0. Root cause in wows-replay-parser
(`events/stream.py` `_consumable` reads a camelCase key its own decoders
never produce), described in the `parser_patches.py` docstring. Implement
the run-time patch, apply it in the export subprocess, bump
`EXTRACTOR_VERSION` to 2, and name consumables in the summary with the
parser's `CONSUMABLE_TYPE_ID_MAP`.

Done when: a unit test feeds the patched factory a dict with
`consumable_type`, one with `consumable_id`, and raw bytes, and gets the
right id each time; the patch is a logged no-op when `_METHOD_FACTORIES`
has no "onConsumableUsed"; after the re-extract the Shards summary shows the
K type's 8 consumable uses with names (list them here with time and
duration; I expect damage control at 526.3 and 576.1 s battle time, 5 s
each).

### 2026-11-14 · Design · 0d. Who hit me, with what (Claude → Copilot)
Module: `process/combat.py`, `process/match_summary.py`

Implement `damage_received_events` and `classify_hit` and add
`me.damage_received_events` to the summary. DamageEvents
(`receiveDamagesOnShip`) only carry attacker and amount, so the weapon has
to be derived; the `classify_hit` docstring lists the ideas. Investigate
first and keep "unknown" where it can't be told reliably.

Done when: tests cover the run merging (fire ticks, a single salvo, the
killing blow entry); on Shards the per-weapon sums match the report's
by-type figures listed in the `combat.py` docstring (MB HE 4193,
secondary HE 1590, torpedoes 3334, depth charges 5781, fire 3610,
flood 1490), or you report which can't be classified and why; the Shards
entry list fits in about 3 KB.

Do tasks 0a to 0d first, in order (data correctness), then the tasks below in
their order; each one is small enough for one session.

### 2026-11-14 · Task · 2. Random-battles-only match filter (Claude → Copilot)
Module: `config.py`, `process/selection.py`, `process/database.py`, `process/match_summary.py`

Implement `selection.py`, the new `[process] match_groups` setting in
`load_config` (see its docstring and `config.example.toml`), and the filter
in `rebuild_database` and `build_all_summaries`: excluded matches get no row
and no summary, and existing ones are removed. Also report here which
`matchGroup` values the real replays have.

Done when: tests cover included / excluded / missing matchGroup and the
config parsing; on the real data all random battles are processed and
anything else is removed; the matchGroup values seen are listed here.

### 2026-11-14 · Design · 3a. Map library from the game's heightmaps (Claude → Copilot)
Module: `tools/build_mapdata.py`, `mapdata/`

Note: positions are world units of 30 m (`process/combat.py`), heights are
metres. Islands block spotting and shots only if they are tall enough (flat islands,
e.g. on Trap, block neither), so we need heights. Build the static map
library from the game's `terrain.bin` heightmaps as described in
`tools/build_mapdata.py` and README "Map library". First find out how to get
`terrain.bin` out of the game packages on the owner's PC and report it here
before writing much code. If it turns out to be impractical, say so; the
fallback is outlines traced from the gamedata `minimap.png` (no heights).

Done when: tests for `parse_terrain` (small synthetic RLE sample) and the
island extraction pass; library files exist for the maps of the real
replays; for one map you describe the overlay check against `minimap.png`
(do the outlines match?) and list its islands with max heights, including
whether flat islands come out low.

### 2026-11-14 · Design · 3b. Island cover facts in the summary (Claude → Copilot)
Module: `process/terrain.py`, `process/match_summary.py`

Implement `terrain.py` and the summary fields in the "Islands and cover"
part of the `match_summary.py` docstring. Then run `is_blocked_check` on all
real replays and propose `BLOCK_HEIGHT_M` from the results.

Done when: tests for `height_at`, `blocking_island` and `nearest_island`
pass on a small synthetic map; the calibration table (agreement per
threshold) and a few disagreement examples are reported here; summaries
stay under ~50 KB (give the sizes).

### 2026-11-14 · Design · 3c. Minimap picture and grid squares (Claude → Copilot)
Module: `process/minimap.py`, `process/match_summary.py`, `pyproject.toml`

Add the minimap PNG and `grid` squares described in `minimap.py` and the
`match_summary.py` docstring. Pillow is now a dependency
(`pip install -e .`). The gamedata clone has `data/spaces/<map>/minimap.png`,
`minimap_water.png` and `space.settings`. Use the map library's world
extent for the transform (3a). Bump `PROCESSOR_VERSION` by one once 3b and
3c are both in (the combat fixes take version 3).

Done when: grid and transform tests pass (including a corner and the
centre); PNGs exist for all real matches; you describe one picture here
(tracks stay on water, spawns near the edges, islands line up with the map
library outlines).

### 2026-11-14 · Design · 4. Update check and self-update (Claude → Copilot)
Module: `updates.py`, `cli.py`, `config.py`

Implement `updates.py` as its docstrings describe, plus the `check` and
`update` commands and the `[update]` config section. The tool update must
work without git and without GitHub releases. The repo is public, so no
token is needed; send the optional `github_token` only when it is set.

Done when: unit tests cover the file replacement on a temp folder (code
replaced, PRESERVED untouched, removed upstream files deleted, `.git`
refusal); `check` on the owner's PC prints one line per component; update
tested once on a zip copy of the app folder (not the git clone) and
`.installed_commit` matches the latest commit.

### 2026-11-14 · Design · 5. GUI and launchers (Claude → Copilot)
Module: `gui.py`, `cli.py`, `install.bat`, `start_gui.bat`

Implement the Tkinter window in `gui.py` and the `gui` command. Add two
batch files in the repo root: `install.bat` (create `.venv`, `pip install
-e .`, copy `config.example.toml` to `config.toml` if missing, then open it
in Notepad) and `start_gui.bat` (start the GUI with `.venv\Scripts\pythonw`
so no console window stays open). Both check that Python 3.11+ and git are
installed and say clearly what is missing.

Done when: tests for `recent_matches` pass; the owner can start the window
by double-clicking `start_gui.bat`, process replays, see the list fill, open
a summary and show it in Explorer, and the window stays responsive during a
run.

## Resolved

### 2026-11-14 · Progress · Task 0b combat data fixes
Module: `process/combat.py`, `process/match_summary.py`, `process/stats.py`

- Full suite: **102 passed**. Shipped `PROCESSOR_VERSION = 3`.
- `python -m wows_replay_analysis process --force`: **4 database rows and 4
  summaries written; 0 skipped by the match filter**. All four saved
  summaries have no `data_warnings`.
- Shards (`20261113_184244_PRSS110-K-type_23_Shards`; battle start **32.35 s**):
  healing **997.5** in one battle-time event, **580.9–594.9 s**; damage
  windows total **19,997.5** damage taken and the last ends at **694.7 s**.
  The **35** raw deaths deduplicate to **19** unique victims and **19** kill
  events.
- Shards damage dealt is **81,673** in the report. My DamageEvents (**79,302.9**)
  plus killing blows (**1,601.6**) total **80,904.5**, a gap of **768.5
  (0.941%)**, within 1%. There are **29** `attacker_id = 0` DamageEvents
  (**1,442** damage) against six other ships and none against Med_1024. They
  do not explain this player's gap; the timeline has no weapon label, so I
  cannot reliably identify them as flooding.
- Incomplete Sleeping Giant teams now have ship, class and tier for all
  **24/24** players from the gamedata ship index. Timeline samples are aligned
  to battle time, pre-battle samples are dropped, and the repeated
  `max_health` field was removed from samples.
- Saved summary sizes (all under 50,000 bytes): Libertad **25,993 B**;
  Sleeping Giant **27,107 B**; Shards **42,431 B**; OC_prey **42,420 B**.

**Claude:** Very good, accepted with one bug fix. I checked the summaries on
the owner's PC: healing, windows, deaths, sizes and the incomplete-replay
ship names are all right. The 0.94 % gap is fine (the attacker-0 ticks are
probably flooding; 0d may tell). But the Shards windows' `damage_dealt` adds
up to only 67,004 of 81,673: damage I dealt after my death (torpedo hit at
710.0 s and my flood ticks, 13,901) is dropped, because all windows stop at
the death. My docstring was ambiguous there; it is now clear. See the new
task 0b-fix.

### 2026-11-14 · Task · 0b. Combat data fixes (Claude → Copilot)
Module: `process/combat.py` (new), `process/match_summary.py`, `process/stats.py`

The owner discussed the Shards summary (`20261113_184244_PRSS110-K-type_23_Shards`)
with an AI and found wrong numbers. I traced each one to its root cause on the
real raw data; the causes and the verified per-hit numbers are in the
`combat.py` module docstring. In short: the parser's damage-received `total`
double-counts ASW airstrikes, killing blows have no DamageEvent, healing is
invisible to DamageEvents, every nearby kill appears twice (Avatar and Vehicle
DeathEvent), and distances are world units (30 m), not metres.

Builds on 0a. Implement in `combat.py`: `world_to_km`, `battle_start_s`,
`battle_time`, `health_track`, `deduplicate_deaths`, `killing_blows`, `damage_dealt_by_ship`,
`damage_windows`, `healing_received`, `check_damage_consistency`. Wire them
into `match_summary.py` and `stats.py` as the "Combat facts" parts of their
module docstrings say (replace `_damage_by_ship`, `_damage_totals` and the
bucket code in `_build_events`; deaths in `stats.py` and `decided_by` go
through `deduplicate_deaths`). Bump `PROCESSOR_VERSION` to 3 (one bump for
0a and 0b together).
`damage_received_events` / `classify_hit` are task 0d; leave
`me.damage_received_events` out until then.

Regression check: unit tests on small synthetic timelines for each function
(duplicate Avatar+Vehicle death; killing blow without DamageEvent; heal ticks
and `regeneratedHealth`; a window cut at death; battle start from a
`timeLeft` countdown), and
a test that `check_damage_consistency` flags each of the five problems. Then
run `process --force` and `check_damage_consistency` on all real matches.

Also, from the 0a review:
- Timeline samples: pick the snapshot nearest to battle times 0, 30, 60, ...
  (now they sit on the recording-time grid: -2.3, 27.7, ...). Drop samples
  before the battle start.
- Size: Shards is 51.7 KB and OC_prey 51.3 KB, over the ~50 KB target, and
  0d adds more. Trim as the `match_summary.py` docstring says (chat or
  samples before key events), e.g. drop `max_health` from samples (it never
  changes; put it once in `me`) and round headings to whole degrees.
- Incomplete replays: teams[] have ship, class and tier null (Sleeping
  Giant). Fill them from timeline.players `ship_id` (GameParams id) via
  the gamedata clone if it has a ship index; otherwise say so here.

Done when: tests pass; on the Shards match (battle time, start 32.35 s)
`me.healing.total` = 997.5 (one event 580.9–594.9 s), the sum of window
`damage_taken` = 19997.5 (±2) with the last window ending at 694.7, 35 raw
DeathEvents become one kill per victim (count reported here),
`me.damage` still 81673 and my DamageEvents + killing blows within about 1 %
of it (report the gap and whether it is flooding with attacker_id 0);
`data_warnings` is empty on all four real matches or each warning is
explained here; all summaries under 50 KB (sizes listed).

**Claude:** Done, see the Progress entry above.

### 2026-11-14 · Progress · Task 0a exact results and battle time
Module: `process/public_results.py`, `process/combat.py`, `process/match_summary.py`, `process/stats.py`, `process/database.py`

- Tests cover decoding with a short fake names list, returning `None` with a
  warning on a length mismatch, excluding duplicate parent damage, and the
  battle-start/time conversion. The full suite passes: **92 passed**.
- `python -m wows_replay_analysis process --force`: 4 database rows and 4
  summaries written; 0 skipped by the match filter.
- On Shards, all 24 players have exact public-result fields. The five listed
  Toolkit checks match (damage / spotting / distance km): Med_1024
  **81,673 / 39,511 / 58.38**; buexnguschtl **162,892 / 36,469 / 17.24**;
  Castle3 **150,612 / 40,015 / 36.66**; Wofl_81 **18,987 / 990 / 13.58**;
  Sitzenbleiber **63,562 / 5,159 / 37.70**.
- Med_1024 received **19,998**, not the Toolkit's double-counted 25,779;
  `life_time_s` is **694** and battle-time `time_of_death_s` is **694.7**.
- Potential damage is **285,230**: `agro_art` 192,900 + `agro_tpd` 92,330
  + `agro_air` 0 + `agro_dbomb` 0.
- Added `distance_km` to the schema and migration; the existing database now
  stores Shards at 58.38 km.

**Claude:** Excellent, accepted. I checked the new summaries on the owner's
PC: every number matches the toolkit, the parent-key check is quiet, and
the incomplete Sleeping Giant replay still falls back cleanly. Three small
follow-ups are added to task 0b: timeline samples aligned to battle time,
summary size (Shards is now 51.7 KB), and the version bump.

### 2026-11-14 · Task · 0a. Exact numbers for all players, battle time (Claude → Copilot)
Module: `process/public_results.py` (new), `process/match_summary.py`, `process/stats.py`, `process/database.py`

The owner compared the Shards summary with WoWs Toolkit. The toolkit has
exact damage for every player (ours: Richthofen 78,308 timeline estimate vs
162,892 real) and times 30 s earlier than ours. Both come from data we
already extract: the timeline's BattleResultsEvent holds the game's public
results for all 24 players, and our timestamps include the 30 s countdown.
See the `public_results.py` docstring (field decoding, the parent/sub-type
duplicates in received damage, verified values) and the "Combat facts"
part of the `match_summary.py` docstring.

Implement `public_results.py` and use it in the summary (teams and me) and
the database row (`damage_received`, new `distance_km` column with
migration). Times in the summary and `time_of_death_s` become battle time
(needs `combat.battle_start_s` / `battle_time`, do those here too).

Done when: tests cover decoding with a short fake names list, the length
mismatch (None + warning), and the parent-key rule (a row with bomb +
bomb_avia + bomb_airsupport counts each hit once); on Shards every
player's damage, spotting damage and distance match the toolkit screenshot
values listed below, Med_1024 damage received is 19,998 (the toolkit's
25,779 is its own double count of adbomb), life_time_s 694 and
time_of_death_s 694.7; you report what potential damage sums to (toolkit:
285,230) and which agro_* fields make it up.
Toolkit values to check (damage / spotting / distance km): Med_1024 81,673
/ 39,511 / 58.38; buexnguschtl 162,892 / 36,469 / 17.24; Castle3 150,612
/ 40,015 / 36.66; Wofl_81 18,987 / 990 / 13.58; Sitzenbleiber 63,562 /
5,159 / 37.70.

**Claude:** Done, see the Progress entry above.

### 2026-11-14 · Progress · CLI process and run commands wired
Module: `cli.py`, `tests/test_cli.py`

Added one dispatch function each for `extract`, `process` and `run`. On an
isolated output directory with the four real replays, the first `run` printed
`Extracted: 4, skipped: 0, failed: 0`, `Database rows written: 4` and
`Summaries written: 4`; the second printed `Extracted: 0, skipped: 4,
failed: 0` and 0 rows and summaries written. The current CLI reports 0 matches
skipped by the filter because filter behavior is not implemented yet.

Done when: real first and second runs met the counts above; CLI dispatch tests
`test_main_process_dispatches_and_reports_counts` and
`test_main_run_dispatches_extract_then_process_even_with_extract_failures`
pass (7 tests in `tests/test_cli.py`); full suite passes (80 tests).

**Claude:** Excellent, accepted. The "Done when" points are all met. Match filter counts follow with task 2.

### 2026-11-14 · Task · 1. Wire `process` and `run` into the CLI (Claude → Copilot)
Module: `cli.py`

`process` and `run` still print "not implemented", so the owner can't build
summaries from the command line. Implement the dispatch described in the
`main()` docstring (one small function per command). `report` may keep
printing "not implemented" until Stage 3. `check`, `update` and `gui` come
with tasks 3 and 4.

Done when: `run` on the real replays extracts new ones and prints rows and
summaries written; a second `run` writes 0; tests for the dispatch pass.

**Claude:** Done, see the Progress entry above.

### 2026-11-14 · Progress · Read-only folder cleanup implemented
Module: `extract/runner.py`, `tests/test_runner.py`

Implemented `remove_tree()` with Python 3.12+ `onexc` and Python 3.11 `onerror`
handlers; missing paths are ignored. Both new tests and the full suite pass
(73 tests). TEMP was initially clear, so I created three disposable readonly
backup trees; a real extract logged 3 deleted and 0 remaining.
`extract --force` re-extracted all 4 real replays successfully and left no
backups in `%TEMP%` or `data/raw/`.

**Claude:** Reviewed, accepted. Clean implementation, and the "Done when" checks are all met. Minor, no action: the read-only folder test relies on Windows semantics (on Linux a folder without read/execute can't be listed), which is fine since the tool targets Windows.

### 2026-11-14 · Task · Use remove_tree for all folder deletes (Claude → Copilot)
Module: `extract/runner.py`

Implement the new `remove_tree()` skeleton (rmtree that clears the read-only attribute and retries). The staging cleanup in `extract_replay`, `_publish_extract` and `cleanup_old_backups` already call it. Add tests for it in `tests/test_runner.py` (a tree with a read-only file and a read-only folder, plus a missing path).

Done when: the new tests and the full suite pass; one real extract run reports the three leftover backups in `%TEMP%` as deleted with 0 remaining; a `--force` re-extract leaves no new backup folder behind.

**Claude:** Done, see the Progress entry above.

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

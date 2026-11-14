# WoWs_Replay_Analysis

A local Python tool that extracts information from World of Warships replay files (`.wowsreplay`) and turns it into summaries for AI-led discussions about your games.

## Goal

The tool produces structured, readable data about your matches that you can hand to an AI assistant to start a discussion, for example: "Here is the data from my latest game. What do you think?"

## Status (2026-11-14)

- **Stage 1 (raw extraction): done.** Both parsers, skip/force, incomplete
  replays, OneDrive-safe cleanup. 4 real replays extracted.
- **Stage 2 (summaries + SQLite): done in code**, verified on 4 replays
  (summaries 47–49 KB). Not yet reachable from the CLI: `process` and `run`
  still print "not implemented" (wiring is the next Copilot task).
- **Next:** first real test, pasting one condensed JSON into an AI chat and
  checking the discussion against a match the owner remembers; then the
  match filter, the minimap picture, updates and the GUI (see
  `docs/COPILOT_NOTES.md` for the task order).
- **Stage 3 (HTML trend reports):** skeleton only.

## Use cases

### 1. Single-match analysis

A detailed summary of one game, focused on **your own play**: what you did and what happened to you. It also includes enough **match context** (allies, enemies, positions, events) to judge whether your decisions made sense given what was happening around you.

### 2. Multi-match trends

Summaries across several games, filtered by ship and time range, for example: "How did I play my Schlieffen this week? Did I improve?" Typical metrics include damage dealt, damage taken, survival time, and how often you died early.

## Architecture

The tool works in three stages.

### Stage 1: Raw extraction

- Parses each replay and extracts **as much raw data as possible**, even data the analysis doesn't use yet.
- Runs **both** community parsers (see [Replay parsers](#replay-parsers)) on every replay and stores both outputs:
  - the **post-battle report** from replays_unpack (about 160 KB of JSON),
  - the **full event timeline** from wows-replay-parser (about 27 MB of JSON, stored gzip-compressed at about 2.4 MB).
- **Why:** the replay format changes between game versions, so older replays may stop being parseable. A raw archive keeps the data usable when the analysis is redesigned later.

### Stage 2: Processing and summaries

- Reads the raw JSON exports and builds two outputs:
  - a **condensed JSON per match**, built mainly from the event timeline, ready to use as context for a single-match AI discussion;
  - **processed statistics** for multi-match trends, built mainly from the post-battle report.
- Stores the processed statistics in a local **SQLite** database for trend queries.
- Can be changed or rebuilt at any time without needing the original replays.

### Stage 3: HTML reports

- Generates **HTML reports** from the SQLite data, for multi-match trends only. Single matches don't need one, because the condensed JSON covers them.
- The reports serve as **context for AI discussions**, and are also readable enough for you to use on your own.

## Replay parsers

Evaluated on 2026-11-14 with two real replays from game version 15.10.0 (build 13533378). Both parsers worked, and each took about 5 seconds per replay. The finished Stage 1 extraction (both parsers, compression, metadata) takes about 7 seconds per replay; the two test timelines held 111,057 and 91,981 events. They complement each other, so the tool uses both.

### Monstrofil/replays_unpack: post-battle report

- Repo: https://github.com/Monstrofil/replays_unpack (MIT license)
- Gives the full **post-battle screen** with named fields: damage dealt and received by weapon type, spotting damage, potential damage, ribbons, kills, XP and credits.
- Also gives a damage map (who damaged whom), death info (killer and weapon), every player's ship, clan and captain skills, and the battle result.
- **No timeline:** no positions, and no information about when things happened.
- Logs a lot of harmless noise (unknown-packet INFO lines, about 48 short-`shipConfigDump` warnings per replay). The CLI hides parser logs below ERROR unless you pass `--verbose`.
- Supports every game version from 0.8.0 onward. CI adds new versions automatically when a patch ships.
- **Install from GitHub, not PyPI.** The PyPI release (3.4.2) only supports up to 14.8.0. Needs `pycryptodomex` and `lxml`.

### toalba/wows-replay-parser: event timeline

- Repo: https://github.com/toalba/wows-replay-parser (Apache 2.0 license)
- Exports a typed, timestamped **event stream** (about 110,000 events per match): positions, shots, torpedoes, damage, deaths, spotting, consumables, capture points, chat and more.
- Takes a **state snapshot** of every ship (health, position, detection) every 5 seconds.
- Events it can't decode yet are kept as `RawEvent` entries, not dropped.
- Its end-of-battle results are an undecoded raw data blob. Use replays_unpack for those.
- Needs the **gamedata repo** https://github.com/toalba/wows-render-gamedata (about 460 MB). Check out the tag that matches the replay's build (`v<build_id>`, e.g. `v13533378`).
- Requires Python 3.11+. It has a single maintainer, which is a risk to keep in mind.
- CLI used: `wowsreplay export <replay> --gamedata <gamedata>/data/scripts_entity/entity_defs -o <out.json>`.
  The tool calls it as `python -c "from wows_replay_parser.cli import main; main()" export ...`
  with the same interpreter, because `python -m wows_replay_parser.cli` has no entry point and does nothing.
  Before `main()` the same code applies our run-time fixes (`extract/parser_patches.py`).

### Not used

- **landaire/wows-toolkit** (Rust): a desktop app with a replay viewer and minimap renderer. It isn't a Python library, but it's useful for checking our results by hand.

## Operation

- A local Python script that you **run on demand**.
- A **configuration file** sets the replay folder. The game saves replays in its installation folder by default.
- Replays that were already processed are **skipped**. They are reprocessed only when the extraction format version changes.

## Match filter

Only **random battles** (`matchGroup` "pvp") are processed for now. Brawls,
events, co-op, ranked and other modes have special rules and would distort the
statistics. Stage 1 still extracts every replay, so the filter can be changed
later (`[process] match_groups` in `config.toml`) and `process` rebuilds the
summaries and database to match.

## Minimap picture

Coordinates alone don't tell an AI where the islands are. Each match summary
therefore comes with `data/matches/<match_id>.png`: the map (water + islands
from the gamedata clone's `data/spaces/<map>/`), the grid, my track with time
labels, and the known tracks of allies and enemies with death markers. Every
position in the JSON also carries its grid square (`"E5"`, rows A–J top to
bottom, columns 1–10 left to right, as on the in-game minimap), so the AI can
read the text and the picture together. Give the AI both files.

## Map library

Islands block both spotting and shots, but only if they are tall enough:
very flat islands (e.g. on Trap) block neither. So the tool needs island
heights, not just outlines.

- **Source:** the game's own terrain heightmaps (`terrain.bin` per map, in
  the game's packed resources, heights in metres). The format is documented
  by landaire's `wowsunpack` (wows-toolkit). No ready-made vector map data
  was found online.
- **Static library:** `tools/build_mapdata.py` reads the installed game and
  writes `mapdata/<map>.json.gz` per map: world extent, a height grid
  (max 256 x 256, metres) and the islands (simplified outline, max height,
  grid squares). The files are committed; the owner reruns the generator
  only when random battles get new or reworked maps.
- **Use in Stage 2** (`process/terrain.py`): the AI is poor at geometry from
  raw coordinates, so Stage 2 computes facts and the summary states them:
  the blocking islands (grid squares, height), my nearest island per
  timeline sample, and for each nearby enemy whether an island blocks the
  line between us. The picture shows the shapes.
- **Blocking rule:** a line is blocked where the terrain along it rises
  above `BLOCK_HEIGHT_M`. The value is calibrated on real replays by
  comparing the rule with the timeline's spotting data.

## Single-match summary sources

- **My numbers** come from the post-battle report (exact).
- **Other players' numbers** come from the game's public results (exact,
  see below). Only incomplete replays use the timeline estimate
  `damage_timeline`.
- **Ship names**: the report only has internal names (`PRSS110_K_type`); the
  summary shows a readable form (`K type`) and keeps the internal one.
- **How the match was decided** (`decided_by`) is derived from the data:
  all ships of one team destroyed, points, or time.

### Data pitfalls found on real replays (2026-11-14)

Checked against the Shards replay of 2026-11-13; details and verified numbers
are in `process/combat.py`.

- **Exact numbers for every player** are in the game's public results
  (timeline `BattleResultsEvent`, complete replays only): damage, damage
  received, spotting, potential damage, life time, distance. They match
  WoWs Toolkit. The timeline estimate `damage_timeline` is only for
  incomplete replays.
- **Damage received**: the game stores some damage twice, as a parent key
  and its sub-types (`bomb`, `tbomb`, `adbomb`, ...). replays_unpack sums
  all keys, and WoWs Toolkit still double-counts `adbomb`. We leave the
  parents out (`process/public_results.py`).
- **Times are battle time**, seconds since the end of the 30 s countdown,
  like the game and WoWs Toolkit. The raw timeline counts from the start
  of the recording.
- **Killing blows have no damage event.** The game sends only the death.
  Damage taken comes from the ship's HP track (`health` updates), and
  damage dealt adds each victim's last HP to the killer.
- **Healing** shows only as HP rises and the `regeneratedHealth` property.
- **Every kill can appear twice** in the timeline (Avatar and Vehicle
  messages). We keep one per victim, the Avatar one.
- **Positions are world units of 30 m.** Distances are reported in km.
- **Consumable ids are 0** in the timeline because of a key mismatch in
  wows-replay-parser. Stage 1 patches it at run time
  (`extract/parser_patches.py`).
- **Damage events have no weapon type.** The attacker is known; the weapon
  is derived from shots, torpedoes and tick patterns where possible.
- Every summary runs consistency checks (totals add up, no duplicate kills)
  and lists any problems in `match.data_warnings`.

## Incomplete replays

A replay stops early when you leave the battle after your ship is destroyed
(the usual case) or when you get disconnected (rare). It then has no battle
result and probably no post-battle screen.

- These matches are still processed. Their result is `unknown`, and
  `end_reason` says `left_after_death` or `disconnected`.
- Their personal numbers come from the timeline and are marked as estimates
  (`stats_source = timeline`).
- Trend reports leave them out of win rates, but keep them for damage,
  survival and early-death statistics.
- Verified on two real replays where the owner left after dying: both have no
  battle result and an empty post-battle screen, and the recording continues
  while spectating until the player leaves (death at 452 s, recording to 591 s).

## Updates

`python -m wows_replay_analysis check` (or **Check for updates** in the GUI)
reports on three components; `update` (or **Update**) updates them:

| Component | Goes out of date when | How it's updated |
|---|---|---|
| Gamedata (wows-render-gamedata) | every game patch | **Automatic** during extraction (checks out tag `v<build>`). `check` only warns when upstream has no tag for the newest replay yet; such replays fail until it does. |
| Parsers (replays_unpack, wows-replay-parser) | game patches that change the replay format | `update` reinstalls both from GitHub with pip. `check` compares the installed commit (pip's `direct_url.json`) with upstream. |
| The tool itself | we push changes | `update` downloads the branch as a zip from the GitHub API and replaces the code files; `config.toml`, `data/`, `cache/` and `.venv/` are never touched. No git and no GitHub releases needed. The installed commit is kept in `.installed_commit`. A git clone (with `.git`) is never overwritten; update it with `git pull`. |

The repo is public, so the update needs no GitHub account or token. The
optional `[update] github_token` only helps if GitHub's anonymous rate limit
(60 API calls per hour) is ever hit.

## GUI

`python -m wows_replay_analysis gui`, or double-click `start_gui.bat`. A
small Tkinter window (no extra install):

- buttons: **Process new replays**, **Check for updates**, **Update**,
  **Open data folder**;
- a list of the 50 most recent processed matches (date, ship, map, result,
  damage), each with **Open** (the summary) and **Show in Explorer**;
- a log pane with the tool's output. Long jobs run in the background, so the
  window stays responsive.

Meant to make the tool easy to use for a non-developer (the owner's brother).

## Setup

**Without git knowledge (e.g. for the brother):** install Python 3.11+ and
Git for Windows (the gamedata download still uses git in the background, it
is never used by hand), download the repo as a zip, unzip it, run
`install.bat` (creates `.venv`, installs the tool, copies the config
template), set `replays_dir` in `config.toml`, then use `start_gui.bat`.
Later updates come through the **Update** button.

**Developer setup:**

1. Install Python 3.11 or newer, and git.
2. Clone this repo and create a virtual environment inside it:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -e .[dev]
   ```
3. Copy `config.example.toml` to `config.toml` and set `replays_dir` to your
   game's replay folder.

The first extraction clones the gamedata repo (about 460 MB) into `cache/`.

**OneDrive:** keep `data_dir` and `gamedata_dir` outside OneDrive-synced
folders (for example `C:/WoWs_Replay_Data/data` and `C:/WoWs_Replay_Data/cache`).
syncing a 460 MB git clone wastes bandwidth. Folders under OneDrive can carry
the read-only attribute, which made plain `shutil.rmtree` fail with WinError 5;
all folder deletes go through `remove_tree()`, which clears it and retries.
Leftover hidden `.<match_id>.backup-*` folders from older runs are harmless;
each extract run deletes them.

## Usage

```
python -m wows_replay_analysis run                 # extract new replays + process them
python -m wows_replay_analysis extract [--force]   # Stage 1 only
python -m wows_replay_analysis process [--force]   # Stage 2 only
python -m wows_replay_analysis report --ship Schlieffen --since 2026-11-07
python -m wows_replay_analysis check               # are updates available?
python -m wows_replay_analysis update              # update parsers + tool
python -m wows_replay_analysis gui                 # desktop window
```

- Single-match discussion: take `data/matches/<match_id>.json` and
  `<match_id>.png` into the chat.
- Trend discussion: take the HTML file from `data/reports/` into the chat, or
  just open it in a browser.

## Project structure

```
.github/copilot-instructions.md   Coding rules for Copilot
config.example.toml               Config template (copy to config.toml)
pyproject.toml                    Package and dependencies
src/wows_replay_analysis/
    cli.py                        Commands: extract, process, report, run, check, update, gui
    config.py                     Loads config.toml
    updates.py                    Update checks and updates (tool, parsers, gamedata)
    gui.py                        Tkinter window
    extract/                      Stage 1
        runner.py                 Finds replays, skips done ones, runs both parsers
        report_parser.py          replays_unpack wrapper (post-battle report)
        timeline_parser.py        wows-replay-parser wrapper (event timeline)
        parser_patches.py         Run-time fixes for wows-replay-parser bugs
        gamedata.py               Keeps the gamedata clone on the right tag
    process/                      Stage 2
        raw_loader.py             Reads one raw extract
        selection.py              Match filter (random battles only by default)
        match_summary.py          Condensed single-match JSON
        combat.py                 HP track, damage, healing, kills, distances, battle time
        public_results.py         Exact post-battle numbers for every player
        minimap.py                Minimap picture per match
        terrain.py                Island heights, cover and line-of-sight facts
        stats.py                  One database row per match
        database.py               SQLite schema and writes
    report/                       Stage 3
        html_report.py            HTML trend report
LICENSE                           MIT license
docs/COPILOT_NOTES.md             Messages between Copilot and Claude
install.bat, start_gui.bat        Setup and launcher for non-developers
mapdata/<map>.json.gz             Map library (committed static data)
tools/build_mapdata.py            Generates the map library from the game
tests/                            pytest tests
```

Local-only files and folders (ignored by git): `config.toml`,
`.installed_commit`, `data/`, `cache/`, `test_data/`, `_tools/`.

## Data layout

```
data/
    raw/<match_id>/               Stage 1, permanent archive
        meta.json                 Replay header, file hash, extractor and parser versions, errors
        report.json               Post-battle report (replays_unpack)
        timeline.json.gz          Event timeline (wows-replay-parser), compressed
    matches/<match_id>.json       Stage 2, condensed single-match summary
    matches/<match_id>.png        Stage 2, minimap picture for the summary
    stats.sqlite                  Stage 2, one row per match
    reports/*.html                Stage 3, trend reports
cache/wows-gamedata/              Gamedata clone used by the timeline parser
```

`match_id` is the replay file name without its extension, for example
`20261113_184244_PRSS110-K-type_23_Shards`.

Versioning: `EXTRACTOR_VERSION` (Stage 1) and `PROCESSOR_VERSION` (Stage 2)
are stored with every output. Raising either one makes the next run redo the
affected matches; everything else is skipped.

## Sharing

The tool should be easy to share. Each user runs their own copy on their own computer, with their own replays and configuration.

## Tech stack

- Python 3.11+
- JSON for raw exports (gzip-compressed for the event timeline)
- Replay parsers: replays_unpack and wows-replay-parser, both installed from GitHub
- SQLite for processed statistics
- Pillow for the minimap pictures, Tkinter for the GUI

Existing community tools (for example, replay parsers) should be used wherever possible instead of building everything from scratch.

## Workflow

- **Claude:** goals and design discussions; writes and maintains the README and instruction files; sets up the code structure (function signatures and docstrings).
- **GitHub Copilot:** implements the functions, following `.github/copilot-instructions.md`. Functions still to be written raise `NotImplementedError`. Copilot reports proposals, questions, issues and progress in `docs/COPILOT_NOTES.md`.

## License

MIT, see `LICENSE`. Third-party parts keep their own licenses: replays_unpack
(MIT), wows-replay-parser (Apache 2.0), wows-render-gamedata (data extracted
from the game). The map library in `mapdata/` is derived from World of
Warships game files, which belong to Wargaming; it is included for
non-commercial, fan-project use only.

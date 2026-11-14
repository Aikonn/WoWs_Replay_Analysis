# WoWs_Replay_Analysis

A local Python tool that extracts information from World of Warships replay files (`.wowsreplay`) and turns it into summaries for AI-led discussions about your games.

## Goal

The tool produces structured, readable data about your matches that you can hand to an AI assistant to start a discussion, for example: "Here is the data from my latest game. What do you think?"

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

### Not used

- **landaire/wows-toolkit** (Rust): a desktop app with a replay viewer and minimap renderer. It isn't a Python library, but it's useful for checking our results by hand.

## Operation

- A local Python script that you **run on demand**.
- A **configuration file** sets the replay folder. The game saves replays in its installation folder by default.
- Replays that were already processed are **skipped**. They are reprocessed only when the extraction format version changes.

## Setup

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

## Usage

```
python -m wows_replay_analysis run                 # extract new replays + process them
python -m wows_replay_analysis extract [--force]   # Stage 1 only
python -m wows_replay_analysis process [--force]   # Stage 2 only
python -m wows_replay_analysis report --ship Schlieffen --since 2026-11-07
```

- Single-match discussion: take `data/matches/<match_id>.json` into the chat.
- Trend discussion: take the HTML file from `data/reports/` into the chat, or
  just open it in a browser.

## Project structure

```
.github/copilot-instructions.md   Coding rules for Copilot
config.example.toml               Config template (copy to config.toml)
pyproject.toml                    Package and dependencies
src/wows_replay_analysis/
    cli.py                        Commands: extract, process, report, run
    config.py                     Loads config.toml
    extract/                      Stage 1
        runner.py                 Finds replays, skips done ones, runs both parsers
        report_parser.py          replays_unpack wrapper (post-battle report)
        timeline_parser.py        wows-replay-parser wrapper (event timeline)
        gamedata.py               Keeps the gamedata clone on the right tag
    process/                      Stage 2
        raw_loader.py             Reads one raw extract
        match_summary.py          Condensed single-match JSON
        stats.py                  One database row per match
        database.py               SQLite schema and writes
    report/                       Stage 3
        html_report.py            HTML trend report
docs/COPILOT_NOTES.md             Messages from Copilot to Claude
tests/                            pytest tests
```

Local-only folders (ignored by git): `config.toml`, `data/`, `cache/`,
`test_data/`, `_tools/`.

## Data layout

```
data/
    raw/<match_id>/               Stage 1, permanent archive
        meta.json                 Replay header, file hash, extractor and parser versions, errors
        report.json               Post-battle report (replays_unpack)
        timeline.json.gz          Event timeline (wows-replay-parser), compressed
    matches/<match_id>.json       Stage 2, condensed single-match summary
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

Existing community tools (for example, replay parsers) should be used wherever possible instead of building everything from scratch.

## Workflow

- **Claude:** goals and design discussions; writes and maintains the README and instruction files; sets up the code structure (function signatures and docstrings).
- **GitHub Copilot:** implements the functions, following `.github/copilot-instructions.md`. Functions still to be written raise `NotImplementedError`. Copilot reports proposals, questions, issues and progress in `docs/COPILOT_NOTES.md`.

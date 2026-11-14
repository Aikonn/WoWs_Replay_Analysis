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
- Stores the result as one **JSON** file per replay, in a readable format.
- **Why:** the replay format changes between game versions, so older replays may stop being parseable. A raw archive keeps the data usable when the analysis is redesigned later.

### Stage 2: Processing and summaries

- Reads the raw JSON exports and builds two outputs: a condensed JSON per match, ready to use as context for a single-match AI discussion, and processed statistics for multi-match trends.
- Stores the processed statistics in a local **SQLite** database for trend queries.
- Can be changed or rebuilt at any time without needing the original replays.

### Stage 3: HTML reports

- Generates **HTML reports** from the SQLite data, for multi-match trends only. Single matches don't need one, because the condensed JSON covers them.
- The reports serve as **context for AI discussions**, and are also readable enough for you to use on your own.

## Operation

- A local Python script that you **run on demand**.
- A **configuration file** sets the replay folder. The game saves replays in its installation folder by default.
- Replays that were already processed are **skipped**. They are reprocessed only when the extraction format version changes.

## Sharing

The tool should be easy to share. Each user runs their own copy on their own computer, with their own replays and configuration.

## Tech stack

- Python
- JSON for raw exports
- SQLite for processed statistics

Existing community tools (for example, replay parsers) should be used wherever possible instead of building everything from scratch.

## Workflow

- **Claude:** goals and design discussions; writes and maintains the README and instruction files; may set up the code structure (function headers and comments).
- **GitHub Copilot:** does at least part of the implementation.

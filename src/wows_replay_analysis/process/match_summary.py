"""Builds the condensed single-match JSON: data/matches/<match_id>.json.

Purpose: context for an AI discussion of one match ("here is my last game,
what do you think?"). It must be small enough to paste into a chat
(target: under about 50 KB) and readable without knowing the replay format.
Use human-readable names (ship names, player names, "battleship"), seconds
from battle start, and round numbers.

First version of the content (to be refined after trying it on real matches):

    match:    id, date/time, map, game mode/scenario, game version, duration,
              result (win/loss/draw) and how it was decided.
    me:       player name, ship (name, class, tier), survived, time of death,
              killed by (player, ship, weapon), and the post-battle numbers:
              damage dealt by weapon type, damage received by type, spotting
              damage, potential damage, frags, ribbons, XP.
    teams:    allies and enemies: player, ship, class, tier, survived,
              damage, frags, XP (post-battle "team_score" tab).
    timeline: samples every 30 s with: my position, heading, health;
              the nearest enemies (ship, distance, visible or not);
              the team scores.
    events:   key moments in order: every kill in the match, damage I dealt
              and took (grouped per 30 s), my consumable use, capture point
              changes, and team chat.

Sources: post-battle numbers from report.json (battle_results_beta), the
timeline and events from timeline.json.gz.
"""

from __future__ import annotations

from pathlib import Path

from wows_replay_analysis.config import Config
from wows_replay_analysis.process.raw_loader import RawMatch


def build_match_summary(raw: RawMatch) -> dict:
    """Return the condensed summary dict for one match (structure above).

    Must still produce a useful summary if the timeline is missing
    (report-only), and the other way round.
    """
    raise NotImplementedError


def write_match_summary(summary: dict, matches_dir: Path, match_id: str) -> Path:
    """Write the summary as pretty-printed UTF-8 JSON and return its path."""
    raise NotImplementedError


def build_all_summaries(config: Config, force: bool = False) -> int:
    """Build summaries for all raw extracts that have none yet or an outdated one.

    Store processor_version inside each summary to detect outdated files.
    Return the number of summaries written.
    """
    raise NotImplementedError

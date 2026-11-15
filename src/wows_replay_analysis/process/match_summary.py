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
    timeline: samples every 30 s with: my position, heading in degrees, health;
              the nearest enemies (ship, distance in km, visible or not);
              the team scores.
    events:   key moments in order: every kill in the match, damage I dealt
              and took (grouped per 30 s), my consumable use, capture point
              changes, and team chat.

Sources: post-battle numbers from report.json (battle_results_beta), the
timeline and events from timeline.json.gz.

Source mapping decisions (2026-11-14, after the first real run):

- Ship names: the report has only internal ship names (e.g. "PRSS110_K_type").
  Show `ship` as a readable name built by readable_ship_name() and keep the
  internal name as `ship_id`. If the gamedata clone turns out to contain
  localized ship names, use them instead and say so in COPILOT_NOTES.
- Damage: superseded by "Combat facts" below. Exact damage for every
  player comes from the public results; `damage_timeline` (estimate) only
  for incomplete replays. Ignore shots_damage_map for totals.
- Result: keep the numeric `victory_type`, and add `decided_by` from
  decided_by(): "all_enemies_destroyed", "all_allies_destroyed", "points",
  "time" or null when unclear. Derive it from the data (alive ships per team
  at the end, final team scores, duration vs the battle time limit), not from
  guessed victory_type codes.
- Timeline samples keep the 3 nearest enemies, each with a `visible` flag.
  Their `ship` labels use readable names; `ship_id` remains internal.
- Incomplete replays (player left after dying, or disconnected): add
  match.replay_complete, match.end_reason and match.recorded_s from
  stats.replay_end(); result "unknown", decided_by null. Fill `me` from the
  timeline where the report has no post-battle screen, and mark those
  numbers as estimates (`stats_source: "timeline"`). Say in the summary
  that events after recorded_s are not known, so the AI doesn't assume
  the battle ended there.
- Keep the whole summary under about 50 KB; the first real ones were 48 KB,
  so new fields must not add much. Trim chat or samples before key events.

Combat facts (2026-11-14, second review; see process/combat.py for the
root causes and the verified numbers):
- Times: every time in the summary (time_s, start_s, end_s,
  time_of_death_s, timeline samples) is battle time, seconds since the
  battle start (combat.battle_time), so it matches the game and WoWs
  Toolkit. Add match.battle_start_s (recording time of the start) and
  match.time_note: "Times are seconds since battle start. In-game clock =
  20:00 minus the time." (use the real battle length). Timeline samples
  are every 30 s of battle time, starting at 0.
- Exact numbers for everyone (process/public_results.py, complete replays):
  each teams[] entry gets damage, damage_received, spotting_damage,
  potential_damage, life_time_s and distance_km; drop damage_timeline
  then. me gets the same, and me.damage_received_by_type =
  public_results.received_damage_breakdown() (replaces the parser's
  section, which double-counts and misses carrier bombers). Incomplete
  replays keep damage_timeline (combat.damage_dealt_by_ship) and take
  damage received from the HP track.
- me.healing = combat.healing_received() (null when none).
- me.max_health is stored once; timeline samples omit it because it does not
  change.
- me.damage_received_events = combat.damage_received_events(): who hit me,
  when, with what, how much. Ticks are merged, so it stays small.
- events: kill events from combat.deduplicate_deaths() (one per victim),
  with `death_reason` kept as a number. damage_summary windows from
  combat.damage_windows() with damage_dealt, damage_taken and healed; the
  window with my death ends at the time of death, and my damage dealt after
  death is kept in windows marked `after_death`.
- teams[].damage_timeline (incomplete replays only) from
  combat.damage_dealt_by_ship() (now includes killing blows; an estimate).
- timeline samples: nearest enemies get `distance_km`
  (combat.world_to_km), not `distance_m`.
- consumable events: `consumable` = the type name from
  wows_replay_parser.consumable_calc.CONSUMABLE_TYPE_ID_MAP (e.g.
  "crashCrew"), plus `duration_s` (work_time_left); drop consumable_id /
  consumable_type. Name null when the id is unknown. Needs a re-extract
  (EXTRACTOR_VERSION 2, see extract/parser_patches.py).
- match.data_warnings: the list from combat.check_damage_consistency(),
  left out when empty, so the AI knows when numbers don't add up.

Minimap and map grid (2026-11-14, see process/minimap.py):
- build_all_summaries also renders data/matches/<match_id>.png with
  minimap.render_minimap() and sets match.minimap = "<match_id>.png" (null if
  the map files are missing; log a warning, never fail the summary).
- Every position in the summary (timeline samples, nearest enemies, kill and
  death positions) gets a `grid` square like "E5" next to it, so the AI can
  connect the JSON to the picture. Add match.grid_note: "Grid as on the
  in-game minimap: rows A-J top to bottom, columns 1-10 left to right."
  To stay under 50 KB, drop raw x/z coordinates where the grid square is
  enough (keep them only in the timeline samples for my own ship).

Islands and cover (2026-11-14, see process/terrain.py and README "Map library"):
- match.islands: compact list of the map's islands that block vision:
  id, grid squares, max_height_m. No outlines (too big, and the AI can't use
  them well; the picture shows the shapes).
- Each timeline sample: me.nearest_island {id, distance_km, direction}, and
  for each listed enemy `blocked_by` (island id or null): whether an island
  stands between me and that enemy.
- Each kill / damage group in events: `blocked_by` for the line between the
  two ships when both positions are known.
- Map not in the library: leave these fields out, log a warning once.

Match filter (2026-11-14, see process/selection.py): only matches whose
matchGroup is in config.match_groups get a summary. Delete existing summary
files (JSON and PNG) of excluded matches, so data/matches/ never shows a
filtered-out match.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from wows_replay_parser.consumable_calc import CONSUMABLE_TYPE_ID_MAP

from wows_replay_analysis.config import Config
from wows_replay_analysis.process import PROCESSOR_VERSION
from wows_replay_analysis.process.combat import (
    battle_start_s,
    battle_time,
    check_damage_consistency,
    damage_dealt_by_ship,
    damage_received_events,
    damage_windows,
    deduplicate_deaths,
    healing_received,
    health_track,
    world_to_km,
)
from wows_replay_analysis.process.public_results import (
    player_numbers,
    public_results,
    received_damage_breakdown,
)
from wows_replay_analysis.process.raw_loader import RawMatch
from wows_replay_analysis.process.raw_loader import list_raw_matches, load_raw_match, own_entity_ids
from wows_replay_analysis.process.stats import match_stats_row

logger = logging.getLogger(__name__)


def build_match_summary(raw: RawMatch, gamedata_dir: Path | None = None) -> dict:
    """Return the condensed summary dict for one match (structure above).

    Must still produce a useful summary if the timeline is missing
    (report-only), and the other way round. Use gamedata_dir to fill ship
    details for incomplete-replay timeline players.
    """
    report = raw.report or {}
    opened = report.get("open") if isinstance(report.get("open"), dict) else {}
    header = raw.meta.get("header")
    header = header if isinstance(header, dict) else {}
    replay_info = {**header, **opened}
    hidden = report.get("hidden") if isinstance(report.get("hidden"), dict) else {}
    timeline = raw.timeline or {}
    timeline_meta = timeline.get("meta") if isinstance(timeline.get("meta"), dict) else {}
    stats = match_stats_row(raw) if raw.report is not None or raw.timeline is not None else {}
    start_s = battle_start_s(timeline)
    public_rows = public_results(raw)
    public_numbers = {
        name: player_numbers(row) for name, row in (public_rows or {}).items()
    }
    ship_catalog = _load_ship_catalog(gamedata_dir) if gamedata_dir is not None else None
    projectile_types = (
        _load_projectile_types(gamedata_dir) if gamedata_dir is not None else None
    )

    players_by_id, players_by_account = _player_indexes(raw, hidden)
    own_ship_id, own_name = _own_player(raw, replay_info, players_by_id)
    own_player = players_by_id.get(own_ship_id) if own_ship_id is not None else None
    own_timeline_player = next(
        (
            player for player in timeline.get("players", [])
            if isinstance(player, dict)
            and _integer_id(player.get("entity_id")) == own_ship_id
        ),
        {},
    ) if isinstance(timeline.get("players"), list) else {}
    own_params_id = _integer_id(
        own_timeline_player.get("ship_id", own_timeline_player.get("ship_params_id"))
    )
    own_catalog_ship = (
        ship_catalog[0].get(str(own_params_id), {})
        if ship_catalog is not None and own_params_id is not None
        else {}
    )
    own_internal_ship_name = (
        own_catalog_ship.get("name")
        if isinstance(own_catalog_ship.get("name"), str)
        else None
    )
    own_catalog_ship_name = (
        ship_catalog[1].get(str(own_params_id))
        if ship_catalog is not None and own_params_id is not None
        else None
    )
    own_ship_name_source = (
        stats.get("ship_name")
        or (own_player or {}).get("ship_id")
        or (own_player or {}).get("ship")
    )
    if stats.get("stats_source") == "timeline" and own_internal_ship_name is not None:
        own_ship_name_source = own_internal_ship_name
        own_ship_display_name = own_catalog_ship_name or readable_ship_name(
            own_internal_ship_name
        )
    else:
        own_ship_display_name = (
            readable_ship_name(own_ship_name_source)
            if isinstance(own_ship_name_source, str)
            else own_catalog_ship_name or readable_ship_name(own_internal_ship_name)
        )
    combat_players_by_id = _damage_event_players(
        players_by_id, timeline, ship_catalog
    )
    own_team = _own_team_id(hidden, own_player)
    damage_by_ship = damage_dealt_by_ship(timeline)
    own_track = health_track(timeline, own_ship_id) if own_ship_id is not None else []
    own_damage_taken = sum(
        previous[1] - current[1]
        for previous, current in zip(own_track, own_track[1:])
        if current[1] < previous[1]
    )
    own_damage = stats.get("damage")
    if own_damage is None and own_ship_id is not None:
        own_damage = damage_by_ship.get(own_ship_id)
    own_damage_received = stats.get("damage_received")
    if own_damage_received is None and own_track:
        own_damage_received = int(round(own_damage_taken))
    if not stats and timeline:
        stats = {
            "damage": own_damage,
            "damage_received": own_damage_received,
            "frags": sum(
                _integer_id(event.get("killer_id")) == own_ship_id
                for event in deduplicate_deaths(timeline.get("events", []))
            ),
        }

    duration = stats.get("duration_s")
    if duration is None:
        raw_duration = _numeric(timeline_meta.get("duration"))
        duration = battle_time(raw_duration, start_s) if raw_duration is not None else None
    if duration is None:
        duration = _numeric(replay_info.get("battleDuration", replay_info.get("duration")))
    event_summaries = _build_events(
        timeline,
        own_ship_id,
        players_by_id,
        players_by_account,
        hidden,
        start_s,
        duration,
    )
    played_at = stats.get("played_at") or _format_date(replay_info.get("dateTime"))
    map_name = (
        stats.get("map_name")
        or replay_info.get("mapDisplayName")
        or _map_basename(timeline_meta.get("map") or replay_info.get("mapName"))
    )
    if isinstance(map_name, str):
        map_name = _map_basename(map_name)
    result_info = hidden.get("battle_result")
    result_info = result_info if isinstance(result_info, dict) else {}
    result = stats.get("result")
    team_lists = _build_teams(
        hidden,
        timeline,
        players_by_id,
        own_team,
        damage_by_ship,
        public_numbers,
        stats.get("replay_complete") == 0,
        ship_catalog,
    )
    own_name = stats.get("player_name") or own_name
    own_public_numbers = public_numbers.get(own_name) if isinstance(own_name, str) else None
    damage_by_type = _section_data(hidden, "details", "damage_to_ships")
    damage_received_by_type = (
        received_damage_breakdown(public_rows[own_name])
        if public_rows is not None and own_name in public_rows
        else _section_data(hidden, "details", "damage_received")
    )
    own_received_report = (
        damage_received_by_type
        if public_rows is not None and own_name in public_rows
        else None
    )
    ribbons = _section_data(hidden, "personal_score", "ribbons")
    ribbon_counts: dict[str, int] = {}
    if isinstance(ribbons, list):
        ribbon_counts = {
            row["name"]: row["count"]
            for row in ribbons
            if isinstance(row, dict)
            and isinstance(row.get("name"), str)
            and isinstance(row.get("count"), int)
            and not isinstance(row.get("count"), bool)
        }

    own_state = _last_own_state(timeline, own_ship_id)
    max_health = _numeric((own_player or {}).get("max_health"))
    if max_health is None and own_track and own_track[0][0] == 0:
        max_health = own_track[0][1]
    final_health = _numeric(own_state.get("health")) if own_state else None
    if final_health is None and own_track:
        final_health = own_track[-1][1]
    if stats.get("survived") is False or stats.get("survived") == 0:
        final_health = 0.0
    healing = healing_received(timeline, own_ship_id) if own_ship_id is not None else None
    if healing is not None:
        healing = {
            "total": healing["total"],
            "events": [
                {
                    **event,
                    "start_s": battle_time(event["start_s"], start_s),
                    "end_s": battle_time(event["end_s"], start_s),
                }
                for event in healing["events"]
            ],
        }
    survived = stats.get("survived")
    if survived is not None:
        survived = bool(survived)
    if survived is None and own_state is not None:
        survived = own_state.get("is_alive")
    own_death_infos = hidden.get("death_info")
    own_death_info = (
        own_death_infos.get(str(own_ship_id))
        if isinstance(own_death_infos, dict) and own_ship_id is not None
        else None
    )
    summary = {
        "processor_version": PROCESSOR_VERSION,
        "match": {
            "id": raw.match_id,
            "date_time": played_at,
            "map": map_name,
            "match_group": stats.get("match_group") or replay_info.get("matchGroup"),
            "scenario": stats.get("scenario") or replay_info.get("scenario"),
            "game_version": stats.get("game_version")
            or replay_info.get("clientVersionFromXml")
            or timeline_meta.get("version"),
            "duration_s": duration,
            "result": result,
            "replay_complete": stats.get("replay_complete"),
            "end_reason": stats.get("end_reason"),
            "recorded_s": stats.get("recorded_s"),
            "battle_start_s": start_s,
            "time_note": (
                "Times are seconds since battle start. In-game clock = 20:00 minus the time."
                if start_s is not None
                else "Battle start was not found; timeline times are recording time."
            ),
            **(
                {"note": "Events after recorded_s are unknown."}
                if stats.get("replay_complete") == 0
                else {}
            ),
            "decided_by": decided_by(raw, own_team),
            "result_decision": {
                "winner_team_id": result_info.get("winner_team_id"),
                "victory_type": result_info.get("victory_type"),
            } if result_info else None,
        },
        "me": {
            "player": stats.get("player_name") or own_name,
            "ship": {
                "name": own_ship_display_name,
                "ship_id": (
                    own_ship_name_source
                    or own_internal_ship_name
                ),
                "class": (
                    stats.get("ship_class")
                    or (own_player or {}).get("class")
                    or own_catalog_ship.get("species")
                ),
                "tier": (
                    stats.get("ship_tier")
                    if stats.get("ship_tier") is not None
                    else (
                        (own_player or {}).get("tier")
                        if (own_player or {}).get("tier") is not None
                        else own_catalog_ship.get("level")
                    )
                ),
            },
            "survived": survived,
            "time_of_death_s": stats.get("time_of_death_s"),
            "killed_by": _killed_by(hidden, own_ship_id, players_by_id),
            "damage": own_damage,
            "damage_dealt_by_type": damage_by_type,
            "damage_received": own_damage_received,
            "damage_received_by_type": damage_received_by_type,
            "spotting_damage": stats.get("spotting_damage"),
            "potential_damage": stats.get("potential_damage"),
            "life_time_s": (
                own_public_numbers.get("life_time_s")
                if own_public_numbers is not None
                else None
            ),
            "distance_km": (
                own_public_numbers.get("distance_km")
                if own_public_numbers is not None
                else None
            ),
            "max_health": max_health,
            "final_health": final_health,
            "damage_taken_changes": sum(
                current[1] < previous[1]
                for previous, current in zip(own_track, own_track[1:])
            ),
            "frags": stats.get("frags", 0),
            "healing": healing,
            "damage_received_events": (
                damage_received_events(
                    timeline,
                    own_ship_id,
                    combat_players_by_id,
                    own_death_info,
                    projectile_types,
                    own_received_report,
                )
                if own_ship_id is not None
                else []
            ),
            "ribbons": ribbon_counts,
            "base_xp": stats.get("base_xp"),
            "stats_source": stats.get("stats_source"),
        },
        "teams": team_lists,
        "timeline": _build_timeline(
            timeline, own_ship_id, own_team, players_by_id, duration, start_s
        ),
        "events": event_summaries,
    }
    warnings = check_damage_consistency(summary)
    if warnings:
        summary["match"]["data_warnings"] = warnings
        for warning in warnings:
            logger.warning("Combat consistency warning for %s: %s", raw.match_id, warning)
    _trim_summary(summary)
    logger.debug("Built match summary for %s", raw.match_id)
    return summary


def readable_ship_name(internal_name: str | None) -> str | None:
    """Turn an internal ship name into a readable one.

    Strip the ship index prefix (letter code + digits, e.g. "PRSS110_") and
    replace underscores with spaces: "PRSS110_K_type" -> "K type",
    "PGSS510_U4501" -> "U4501". Return the input unchanged if it doesn't
    match that pattern, and None for None.
    """
    if internal_name is None:
        return None
    match = re.fullmatch(r"[A-Za-z]+\d+_(.+)", internal_name)
    if match is None:
        return internal_name
    return match.group(1).replace("_", " ")


def decided_by(raw: RawMatch, own_team: int | None) -> str | None:
    """Return how the match was decided, from the data rather than codes.

    "all_enemies_destroyed" / "all_allies_destroyed" when one team has no
    ships alive at the end; "points" when a team reached the score limit;
    "time" when the battle ran to its time limit; None when unclear.
    Use report data where available and the timeline otherwise.
    """
    hidden = raw.report.get("hidden", {}) if isinstance(raw.report, dict) else {}
    hidden = hidden if isinstance(hidden, dict) else {}
    battle_result = hidden.get("battle_result")
    winner = battle_result.get("winner_team_id") if isinstance(battle_result, dict) else None
    complete = (
        isinstance(winner, int) and not isinstance(winner, bool)
    ) or _has_timeline_battle_end(raw.timeline)
    if not complete or own_team is None:
        return None

    alive_by_team = _report_alive_by_team(hidden)
    if alive_by_team is None:
        alive_by_team = _timeline_alive_by_team(raw.timeline)
    if alive_by_team is not None:
        eliminated = [team for team, alive in alive_by_team.items() if not alive]
        if own_team in eliminated:
            return "all_allies_destroyed"
        if any(team != own_team for team in eliminated):
            return "all_enemies_destroyed"

    scores = _last_team_scores(raw.timeline)
    # WoWs ends a match when a team reaches the 1,000-point limit.
    if scores and any(score >= 1000 for score in scores.values()):
        return "points"

    opened = raw.report.get("open", {}) if isinstance(raw.report, dict) else {}
    opened = opened if isinstance(opened, dict) else {}
    duration_limit = opened.get("battleDuration")
    if duration_limit is None:
        duration_limit = opened.get("duration")
    time_limit = _numeric(duration_limit)
    timeline = raw.timeline if isinstance(raw.timeline, dict) else {}
    snapshots = timeline.get("state_snapshots")
    if isinstance(snapshots, list) and snapshots:
        last_battle = snapshots[-1].get("battle") if isinstance(snapshots[-1], dict) else None
        time_left = _numeric(last_battle.get("time_left")) if isinstance(last_battle, dict) else None
        if time_left is not None and time_left <= 0:
            return "time"
    meta = timeline.get("meta")
    recorded_duration = _numeric(meta.get("duration")) if isinstance(meta, dict) else None
    if (
        time_limit is not None
        and recorded_duration is not None
        and recorded_duration >= time_limit
    ):
        return "time"
    return None


def _has_timeline_battle_end(timeline: dict | None) -> bool:
    events = timeline.get("events") if isinstance(timeline, dict) else None
    return isinstance(events, list) and any(
        isinstance(event, dict) and event.get("event_type") == "BattleEndEvent"
        for event in events
    )


def _report_alive_by_team(hidden: dict) -> dict[int, bool] | None:
    players = hidden.get("players")
    if isinstance(players, dict):
        entries = list(players.values())
    elif isinstance(players, list):
        entries = players
    else:
        entries = []
    counts: dict[int, list[bool]] = {}
    for player in entries:
        if not isinstance(player, dict):
            return None
        team = _integer_id(player.get("teamId"))
        alive = player.get("isAlive")
        if team is None or not isinstance(alive, bool):
            return None
        counts.setdefault(team, []).append(alive)
    if len(counts) < 2:
        return None
    return {team: any(states) for team, states in counts.items()}


def _timeline_alive_by_team(timeline: dict | None) -> dict[int, bool] | None:
    if not isinstance(timeline, dict):
        return None
    players = timeline.get("players")
    snapshots = timeline.get("state_snapshots")
    events = timeline.get("events")
    if (
        not isinstance(players, list)
        or not players
        or not isinstance(snapshots, list)
        or not snapshots
    ):
        return None
    last_snapshot = snapshots[-1]
    ships = last_snapshot.get("ships") if isinstance(last_snapshot, dict) else None
    if not isinstance(ships, dict):
        return None
    deaths = {
        _integer_id(event.get("victim_id", event.get("entity_id")))
        for event in deduplicate_deaths(events)
    } if isinstance(events, list) else set()
    counts: dict[int, list[bool]] = {}
    for player in players:
        if not isinstance(player, dict):
            return None
        team = _integer_id(player.get("team_id"))
        ship_id = _integer_id(player.get("entity_id"))
        if team is None or ship_id is None:
            return None
        state = ships.get(str(ship_id), ships.get(ship_id))
        alive = state.get("is_alive") if isinstance(state, dict) else None
        if not isinstance(alive, bool):
            health = _numeric(state.get("health")) if isinstance(state, dict) else None
            alive = False if ship_id in deaths or (health is not None and health <= 0) else None
        if alive is None:
            return None
        counts.setdefault(team, []).append(alive)
    if len(counts) < 2:
        return None
    return {team: any(states) for team, states in counts.items()}


def _last_team_scores(timeline: dict | None) -> dict[int, float]:
    if not isinstance(timeline, dict):
        return {}
    snapshots = timeline.get("state_snapshots")
    if not isinstance(snapshots, list):
        return {}
    for snapshot in reversed(snapshots):
        battle = snapshot.get("battle") if isinstance(snapshot, dict) else None
        scores = battle.get("team_scores") if isinstance(battle, dict) else None
        if not isinstance(scores, dict):
            continue
        parsed: dict[int, float] = {}
        for key, value in scores.items():
            team = _integer_id(key)
            score = _numeric(value)
            if team is not None and score is not None:
                parsed[team] = score
        if parsed:
            return parsed
    return {}


def write_match_summary(summary: dict, matches_dir: Path, match_id: str) -> Path:
    """Write the summary as pretty-printed UTF-8 JSON and return its path."""
    if not match_id or Path(match_id).name != match_id:
        raise ValueError(f"Invalid match id for summary path: {match_id!r}")
    matches_dir.mkdir(parents=True, exist_ok=True)
    output_path = matches_dir / f"{match_id}.json"
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{match_id}.", suffix=".tmp", dir=matches_dir
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output_file:
            json.dump(summary, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
        os.replace(temp_path, output_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return output_path


def build_all_summaries(config: Config, force: bool = False) -> int:
    """Build summaries for all raw extracts that have none yet or an outdated one.

    Store processor_version inside each summary to detect outdated files.
    Return the number of summaries written.

    Skip matches excluded by selection.is_included(raw, config.match_groups)
    and remove their old summary files. Render the minimap PNG for each
    written summary (needs config.gamedata_dir; the gamedata clone is already
    on the right tag after extraction, but check the map folder exists).
    Loading only meta.json is enough to apply the filter: use
    load_raw_match(match_dir, with_timeline=False) first, and load the
    timeline only for included matches.
    """
    written = 0
    config.matches_dir.mkdir(parents=True, exist_ok=True)
    for match_dir in list_raw_matches(config.raw_dir):
        match_id = match_dir.name
        output_path = config.matches_dir / f"{match_id}.json"
        if not force and not _summary_is_outdated(output_path):
            continue
        try:
            raw = load_raw_match(match_dir)
            summary = build_match_summary(raw, config.gamedata_dir)
            write_match_summary(summary, config.matches_dir, match_id)
            written += 1
        except Exception:
            logger.exception("Could not build summary for %s", match_id)
    return written


def _section_data(hidden: dict, tab_name: str, section_name: str) -> object:
    beta = hidden.get("battle_results_beta")
    tabs = beta.get("tabs") if isinstance(beta, dict) else None
    tab = tabs.get(tab_name) if isinstance(tabs, dict) else None
    sections = tab.get("sections") if isinstance(tab, dict) else None
    section = sections.get(section_name) if isinstance(sections, dict) else None
    return section.get("data") if isinstance(section, dict) else None


def _player_indexes(
    raw: RawMatch, hidden: dict
) -> tuple[dict[int, dict], dict[int, dict]]:
    by_id: dict[int, dict] = {}
    by_account: dict[int, dict] = {}
    report_players = hidden.get("players")
    if isinstance(report_players, dict):
        for player in report_players.values():
            if not isinstance(player, dict):
                continue
            ship_id = _integer_id(player.get("shipId"))
            if ship_id is None:
                continue
            entry = {
                "name": player.get("name"),
                "team_id": player.get("teamId"),
                "account_id": _integer_id(player.get("id")),
                "entity_id": ship_id,
                "alive": player.get("isAlive"),
            }
            by_id[ship_id] = entry
            account_id = entry["account_id"]
            if account_id is not None:
                by_account[account_id] = entry

    score_rows = _team_score_rows(hidden)
    for row in score_rows:
        name = row.get("username")
        player = next((entry for entry in by_id.values() if entry.get("name") == name), None)
        if player is None:
            timeline_players = raw.timeline.get("players", []) if raw.timeline else []
            player = next(
                (
                    {
                        "name": entry.get("name"),
                        "team_id": entry.get("team_id"),
                        "account_id": _integer_id(entry.get("account_id")),
                        "entity_id": _integer_id(entry.get("entity_id")),
                    }
                    for entry in timeline_players
                    if isinstance(entry, dict) and entry.get("name") == name
                ),
                None,
            )
        if player is None:
            player = {"name": name}
        player.update({
            "ship": row.get("ship_name"),
            "ship_id": row.get("ship_name"),
            "class": row.get("ship_type"),
            "tier": row.get("ship_level"),
            "alive": row.get("is_alive"),
            "frags": row.get("frags"),
            "xp": row.get("exp"),
            "team_id": row.get("team_id", player.get("team_id")),
        })
        ship_id = next(
            (
                _integer_id(entry.get("shipId"))
                for entry in report_players.values()
                if isinstance(report_players, dict)
                and isinstance(entry, dict)
                and entry.get("name") == name
            ),
            None,
        ) if isinstance(report_players, dict) else None
        if ship_id is None and raw.timeline:
            timeline_players = raw.timeline.get("players", [])
            ship_id = next(
                (
                    _integer_id(entry.get("entity_id"))
                    for entry in timeline_players
                    if isinstance(entry, dict) and entry.get("name") == name
                ),
                None,
            )
        if ship_id is not None:
            by_id[ship_id] = player
        account_id = player.get("account_id")
        if isinstance(account_id, int):
            by_account[account_id] = player

    if raw.timeline:
        for player in raw.timeline.get("players", []):
            if not isinstance(player, dict):
                continue
            entity_id = _integer_id(player.get("entity_id"))
            if entity_id is None:
                continue
            entry = by_id.setdefault(entity_id, {})
            entry.update({
                key: value
                for key, value in {
                    "name": player.get("name"),
                    "team_id": player.get("team_id"),
                    "account_id": _integer_id(player.get("account_id")),
                    "entity_id": entity_id,
                    "ship_id": player.get("ship"),
                    "max_health": player.get("max_health"),
                }.items()
                if value is not None
            })
            account_id = _integer_id(player.get("account_id"))
            if account_id is not None:
                by_account[account_id] = entry
    return by_id, by_account


def _team_score_rows(hidden: dict) -> list[dict]:
    beta = hidden.get("battle_results_beta")
    tabs = beta.get("tabs") if isinstance(beta, dict) else None
    team_score = tabs.get("team_score") if isinstance(tabs, dict) else None
    all_sections = team_score.get("sections") if isinstance(team_score, dict) else None
    rows: list[dict] = []
    if isinstance(all_sections, dict):
        for section in all_sections.values():
            data = section.get("data") if isinstance(section, dict) else None
            if isinstance(data, list):
                rows.extend(row for row in data if isinstance(row, dict))
    return rows


def _own_player(raw: RawMatch, replay_info: dict, players_by_id: dict[int, dict]) -> tuple[int | None, str | None]:
    if raw.report is not None:
        try:
            _, ship_id = own_entity_ids(raw)
            return ship_id, players_by_id.get(ship_id, {}).get("name")
        except ValueError:
            logger.debug("Could not get own ship id from report for %s", raw.match_id)
    name = replay_info.get("playerName")
    if isinstance(name, str):
        for ship_id, player in players_by_id.items():
            if player.get("name") == name:
                return ship_id, name
    return None, name if isinstance(name, str) else None


def _own_team_id(hidden: dict, own_player: dict | None) -> int | None:
    for row in _team_score_rows(hidden):
        if row.get("is_own"):
            return _integer_id(row.get("team_id"))
    return _integer_id(own_player.get("team_id")) if own_player else None


def _build_teams(
    hidden: dict,
    timeline: dict,
    players_by_id: dict[int, dict],
    own_team: int | None,
    damage_by_ship: dict[int, float],
    public_numbers: dict[str, dict],
    incomplete: bool,
    ship_catalog: tuple[dict[str, dict], dict[str, str]] | None,
) -> dict[str, list[dict]]:
    beta = hidden.get("battle_results_beta")
    tabs = beta.get("tabs") if isinstance(beta, dict) else None
    team_score = tabs.get("team_score") if isinstance(tabs, dict) else None
    sections = team_score.get("sections") if isinstance(team_score, dict) else None
    teams: dict[str, list[dict]] = {"allies": [], "enemies": []}
    if isinstance(sections, dict):
        for section_name, team_name in (("allies", "allies"), ("enemies", "enemies")):
            rows = sections.get(section_name, {})
            data = rows.get("data") if isinstance(rows, dict) else None
            if isinstance(data, list):
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    player = next(
                        (
                            value for value in players_by_id.values()
                            if value.get("name") == row.get("username")
                        ),
                        {},
                    )
                    entry = {
                        "player": row.get("username"),
                        "ship": readable_ship_name(
                            row.get("ship_name") or player.get("ship_id") or player.get("ship")
                        ),
                        "ship_id": (
                            row.get("ship_name") or player.get("ship_id") or player.get("ship")
                        ),
                        "class": row.get("ship_type"),
                        "tier": row.get("ship_level"),
                        "survived": row.get("is_alive"),
                        "frags": row.get("frags"),
                        "xp": row.get("exp"),
                    }
                    exact = public_numbers.get(row.get("username"))
                    if exact is not None:
                        entry.update(exact)
                    elif incomplete:
                        entry["damage_timeline"] = _damage_for_player(
                            timeline, player, damage_by_ship
                        )
                    teams[team_name].append(entry)
    if isinstance(timeline.get("players"), list):
        for player in timeline["players"]:
            if not isinstance(player, dict):
                continue
            team_name = "allies" if player.get("team_id") == own_team else "enemies"
            ship_id = _integer_id(player.get("entity_id"))
            if any(entry.get("player") == player.get("name") for entry in teams[team_name]):
                continue
            entry = players_by_id.get(ship_id, {})
            params_id = _integer_id(player.get("ship_id", player.get("ship_params_id")))
            ship_details = (
                ship_catalog[0].get(str(params_id), {})
                if ship_catalog is not None and params_id is not None
                else {}
            )
            ship_name = (
                ship_catalog[1].get(str(params_id))
                if ship_catalog is not None and params_id is not None
                else None
            )
            internal_ship_name = ship_details.get("name")
            result = {
                "player": player.get("name"),
                "ship": ship_name or (
                    readable_ship_name(internal_ship_name)
                    if isinstance(internal_ship_name, str)
                    else entry.get("ship") or player.get("ship")
                ),
                "ship_id": internal_ship_name or entry.get("ship_id") or player.get("ship"),
                "class": ship_details.get("species") or entry.get("class"),
                "tier": ship_details.get("level", entry.get("tier")),
                "survived": entry.get("alive"),
                "frags": entry.get("frags"),
                "xp": entry.get("xp"),
            }
            exact = public_numbers.get(player.get("name"))
            if exact is not None:
                result.update(exact)
            elif incomplete:
                result["damage_timeline"] = _damage_for_player(
                    timeline, entry, damage_by_ship
                )
            teams[team_name].append(result)
    return teams


def _damage_for_player(
    timeline: dict, player: dict, damage_by_ship: dict[int, float]
) -> int | float | None:
    ship_id = _integer_id(player.get("entity_id"))
    events = timeline.get("events")
    if ship_id is None or not isinstance(events, list):
        return None
    return damage_by_ship.get(ship_id, 0.0)


def _build_timeline(
    timeline: dict,
    own_ship_id: int | None,
    own_team: int | None,
    players_by_id: dict[int, dict],
    duration: object,
    start_s: float | None,
) -> list[dict]:
    snapshots = timeline.get("state_snapshots")
    if own_ship_id is None or not isinstance(snapshots, list) or not snapshots:
        return []
    valid = [
        snapshot for snapshot in snapshots
        if isinstance(snapshot, dict) and _numeric(snapshot.get("timestamp")) is not None
    ]
    if not valid:
        return []
    timed = [
        (snapshot, battle_time(float(snapshot["timestamp"]), start_s))
        for snapshot in valid
    ]
    timed = [(snapshot, timestamp) for snapshot, timestamp in timed if timestamp >= 0]
    if not timed:
        return []
    max_time = _numeric(duration)
    if max_time is None:
        max_time = max(battle_timestamp for _, battle_timestamp in timed)
    meta = timeline.get("meta")
    interval = _numeric(meta.get("snapshot_interval")) if isinstance(meta, dict) else None
    tolerance = max(2.5, (interval or 5.0) / 2 + 0.1)
    enemy_ids = [
        player_id for player_id, player in players_by_id.items()
        if player_id != own_ship_id
        and own_team is not None
        and player.get("team_id") is not None
        and player.get("team_id") != own_team
    ]

    samples: list[dict] = []
    seen_timestamps: set[float] = set()
    targets = range(0, math.floor(max_time / 30) * 30 + 1, 30)
    for target in targets:
        snapshot, battle_timestamp = min(
            timed, key=lambda item: abs(item[1] - target)
        )
        timestamp = float(snapshot["timestamp"])
        if abs(battle_timestamp - target) > tolerance or timestamp in seen_timestamps:
            continue
        seen_timestamps.add(timestamp)
        ships = snapshot.get("ships")
        if not isinstance(ships, dict):
            continue
        own_state = ships.get(str(own_ship_id), ships.get(own_ship_id))
        if not isinstance(own_state, dict):
            continue
        own_position = _position(own_state.get("position"))
        nearest: list[dict] = []
        if own_position is not None:
            for enemy_id in enemy_ids:
                state = ships.get(str(enemy_id), ships.get(enemy_id))
                position = _position(state.get("position")) if isinstance(state, dict) else None
                if state is None or position is None:
                    continue
                distance = math.sqrt(
                    (position[0] - own_position[0]) ** 2
                    + (position[2] - own_position[2]) ** 2
                )
                player = players_by_id[enemy_id]
                ship_id = player.get("ship_id") or player.get("ship")
                nearest.append({
                    "player": player.get("name"),
                    "ship": readable_ship_name(
                        ship_id if isinstance(ship_id, str) else None
                    ),
                    "distance_km": world_to_km(distance),
                    "visible": state.get("is_detected"),
                })
            nearest.sort(key=lambda item: item["distance_km"])
        battle = snapshot.get("battle")
        battle = battle if isinstance(battle, dict) else {}
        samples.append({
            "time_s": battle_timestamp,
            "position": own_position,
            "heading": (
                round(math.degrees(heading)) % 360
                if (heading := _numeric(own_state.get("yaw"))) is not None
                else None
            ),
            "health": own_state.get("health"),
            "nearest_enemies": nearest[:3],
            "team_scores": battle.get("team_scores"),
        })
    return samples


def _build_events(
    timeline: dict,
    own_ship_id: int | None,
    players_by_id: dict[int, dict],
    players_by_account: dict[int, dict],
    hidden: dict,
    start_s: float | None,
    duration_s: object,
) -> list[dict]:
    events = timeline.get("events")
    if not isinstance(events, list):
        return []
    summaries: list[dict] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type")
        timestamp = _numeric(event.get("timestamp"))
        if timestamp is None:
            continue
        battle_timestamp = battle_time(timestamp, start_s)
        if (
            event_type == "ConsumableEvent"
            and own_ship_id is not None
            and _integer_id(event.get("vehicle_id", event.get("entity_id"))) == own_ship_id
            and event.get("is_used") is True
        ):
            consumable_type = _integer_id(event.get("consumable_type"))
            summaries.append({
                "type": "consumable",
                "time_s": battle_timestamp,
                "consumable": CONSUMABLE_TYPE_ID_MAP.get(consumable_type),
                "duration_s": (
                    round(duration_value, 1)
                    if (duration_value := _numeric(event.get("work_time_left"))) is not None
                    else None
                ),
            })
        elif event_type == "CapturePointUpdateEvent":
            summaries.append({
                "type": "capture_point",
                "time_s": battle_timestamp,
                "zone_id": event.get("zone_entity_id", event.get("entity_id")),
                "team_id": event.get("team_id"),
                "progress": event.get("progress"),
                "invader_team": event.get("invader_team"),
                "has_invaders": event.get("has_invaders"),
            })
        elif event_type == "ChatEvent" and event.get("channel") == "battle_team":
            sender_id = _integer_id(event.get("sender_id"))
            sender = players_by_account.get(sender_id) if sender_id is not None else None
            summaries.append({
                "type": "team_chat",
                "time_s": battle_timestamp,
                "player": sender.get("name") if sender else None,
                "message": event.get("message"),
            })

    for death in deduplicate_deaths(events):
        timestamp = _numeric(death.get("timestamp"))
        victim_id = _integer_id(death.get("victim_id", death.get("entity_id")))
        killer_id = _integer_id(death.get("killer_id"))
        if timestamp is None:
            continue
        death_info = hidden.get("death_info")
        details = death_info.get(str(victim_id), {}) if isinstance(death_info, dict) else {}
        summaries.append({
            "type": "kill",
            "time_s": battle_time(timestamp, start_s),
            "victim": _player_reference(players_by_id.get(victim_id), victim_id),
            "killer": _player_reference(players_by_id.get(killer_id), killer_id),
            "weapon": details.get("name") if isinstance(details, dict) else None,
            "victim_id": victim_id,
            "killer_id": killer_id,
            "death_reason": death.get("death_reason"),
        })
    for window in damage_windows(
        timeline,
        own_ship_id,
        _numeric(duration_s),
    ) if own_ship_id is not None else []:
        summaries.append({"type": "damage_summary", **window})
    summaries.sort(key=lambda event: event.get("time_s", event.get("start_s", 0)))
    return summaries


def _load_ship_catalog(
    gamedata_dir: Path,
) -> tuple[dict[str, dict], dict[str, str]] | None:
    ships_path = gamedata_dir / "data" / "ships.json"
    names_path = gamedata_dir / "data" / "ship_names.json"
    try:
        with ships_path.open("r", encoding="utf-8") as file:
            ships = json.load(file)
        with names_path.open("r", encoding="utf-8") as file:
            names = json.load(file)
    except FileNotFoundError:
        logger.info("Gamedata ship index is missing under %s", gamedata_dir)
        return None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        logger.exception("Could not read the gamedata ship index under %s", gamedata_dir)
        return None
    if not isinstance(ships, dict) or not isinstance(names, dict):
        logger.warning("Invalid gamedata ship index under %s", gamedata_dir)
        return None
    return (
        {
            str(key): value
            for key, value in ships.items()
            if isinstance(value, dict)
        },
        {
            str(key): value
            for key, value in names.items()
            if isinstance(value, str)
        },
    )


def _load_projectile_types(gamedata_dir: Path) -> dict[int, str] | None:
    """Load GAMEPARAMS_ID-to-ammo-type mappings for hit classification."""
    projectiles_path = gamedata_dir / "data" / "projectiles.json"
    try:
        with projectiles_path.open("r", encoding="utf-8") as file:
            projectiles = json.load(file)
    except FileNotFoundError:
        logger.info("Gamedata projectile index is missing under %s", gamedata_dir)
        return None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        logger.exception("Could not read the projectile index under %s", gamedata_dir)
        return None
    if not isinstance(projectiles, dict):
        logger.warning("Invalid projectile index under %s", gamedata_dir)
        return None
    return {
        int(params_id): projectile["a"]
        for params_id, projectile in projectiles.items()
        if params_id.isdigit()
        and isinstance(projectile, dict)
        and isinstance(projectile.get("a"), str)
    }


def _damage_event_players(
    players_by_id: dict[int, dict],
    timeline: dict,
    ship_catalog: tuple[dict[str, dict], dict[str, str]] | None,
) -> dict[int, dict]:
    """Add readable ship references for attackers, including incomplete reports."""
    timeline_players = timeline.get("players")
    if not isinstance(timeline_players, list):
        timeline_players = []
    timeline_by_id = {
        entity_id: player
        for player in timeline_players
        if isinstance(player, dict)
        and (entity_id := _integer_id(player.get("entity_id"))) is not None
    }
    result: dict[int, dict] = {}
    for entity_id in set(players_by_id) | set(timeline_by_id):
        player = dict(players_by_id.get(entity_id, {}))
        timeline_player = timeline_by_id.get(entity_id, {})
        params_id = _integer_id(
            timeline_player.get("ship_id", timeline_player.get("ship_params_id"))
        )
        details = (
            ship_catalog[0].get(str(params_id), {})
            if ship_catalog is not None and params_id is not None
            else {}
        )
        internal_name = (
            details.get("name")
            if isinstance(details.get("name"), str)
            else player.get("ship_id") or player.get("ship")
        )
        catalog_name = (
            ship_catalog[1].get(str(params_id))
            if ship_catalog is not None and params_id is not None
            else None
        )
        player.update({
            "name": player.get("name") or timeline_player.get("name"),
            "ship_id": internal_name,
            "ship": (
                catalog_name
                or readable_ship_name(internal_name)
                if isinstance(internal_name, str)
                else None
            ),
        })
        result[entity_id] = player
    return result


def _trim_summary(summary: dict) -> None:
    """Trim lower-priority chat and samples if the JSON exceeds the size target."""
    events = summary.get("events")
    timeline = summary.get("timeline")

    def size_bytes() -> int:
        return len(
            json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8")
        )

    while size_bytes() >= 50_000 and isinstance(events, list):
        chat_index = next(
            (
                index for index, event in enumerate(events)
                if isinstance(event, dict) and event.get("type") == "team_chat"
            ),
            None,
        )
        if chat_index is None:
            break
        events.pop(chat_index)
    while (
        size_bytes() >= 50_000
        and isinstance(timeline, list)
        and len(timeline) > 2
    ):
        timeline.pop(len(timeline) // 2)


def _killed_by(hidden: dict, own_ship_id: int | None, players_by_id: dict[int, dict]) -> dict | None:
    if own_ship_id is None:
        return None
    death_info = hidden.get("death_info")
    info = death_info.get(str(own_ship_id)) if isinstance(death_info, dict) else None
    if not isinstance(info, dict):
        return None
    killer_id = _integer_id(info.get("killer_id"))
    return {
        "player": _player_reference(
            players_by_id.get(killer_id), killer_id
        ) if killer_id is not None else None,
        "weapon": info.get("name"),
    }


def _player_reference(player: dict | None, player_id: int | None) -> dict | None:
    if player is None and player_id is None:
        return None
    player = player or {}
    ship_id = player.get("ship_id") or player.get("ship")
    return {
        "name": player.get("name"),
        "ship": readable_ship_name(ship_id),
        "class": player.get("class"),
        "tier": player.get("tier"),
    }


def _last_own_state(timeline: dict, own_ship_id: int | None) -> dict | None:
    snapshots = timeline.get("state_snapshots")
    if own_ship_id is None or not isinstance(snapshots, list):
        return None
    for snapshot in reversed(snapshots):
        ships = snapshot.get("ships") if isinstance(snapshot, dict) else None
        state = ships.get(str(own_ship_id), ships.get(own_ship_id)) if isinstance(ships, dict) else None
        if isinstance(state, dict):
            return state
    return None


def _position(value: object) -> tuple[float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    x = _numeric(value[0])
    y = _numeric(value[1])
    z = _numeric(value[2])
    if x is None or y is None or z is None:
        return None
    return x, y, z


def _integer_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _format_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%d.%m.%Y %H:%M:%S").isoformat(sep=" ")
    except ValueError:
        try:
            return datetime.fromisoformat(value).isoformat(sep=" ")
        except ValueError:
            return value


def _map_basename(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.rsplit("/", 1)[-1]


def _summary_is_outdated(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as summary_file:
            summary = json.load(summary_file)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return True
    if not isinstance(summary, dict):
        return True
    version = summary.get("processor_version")
    return isinstance(version, bool) or not isinstance(version, int) or version < PROCESSOR_VERSION

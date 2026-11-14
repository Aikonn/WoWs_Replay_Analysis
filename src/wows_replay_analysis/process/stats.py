"""Turns one raw extract into the database row for the multi-match statistics.

Built mainly from the post-battle report (report.json); incomplete replays use
the timeline for estimates when report sections are not available.

Incomplete replays: when the player leaves the battle after dying (common)
or gets disconnected (rare), the replay stops early. It then has no battle
result (hidden.battle_result is null) and an empty post-battle screen
(battle_results_beta.tabs is {}); verified on two real replays. The
recording continues while the player spectates, until he leaves. Such a
replay must still produce a row:
- result = "unknown", replay_complete = 0, end_reason from replay_end().
- Damage, frags, damage received, spotting etc. fall back to the timeline
  where it has them (stats_source = "timeline"); values the timeline can't
  give stay NULL. Never fail just because report sections are missing.
- survived / time_of_death_s still come from the timeline.
Trend reports must exclude result "unknown" from win rates but keep these
matches for damage, survival and early-death statistics.

Combat facts (2026-11-14): damage_received comes from
public_results.received_damage_breakdown() (the parser's `total`
double-counts). time_of_death_s is battle time (combat.battle_time); add a
distance_km column from public_results.player_numbers() (schema change).
Timeline fallbacks use process/combat.py: damage received from the HP track
(health_track), damage dealt from DamageEvents plus killing_blows(), and
deaths only through deduplicate_deaths().
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from numbers import Real

from wows_replay_analysis.process import PROCESSOR_VERSION
from wows_replay_analysis.process.combat import battle_start_s, battle_time
from wows_replay_analysis.process.public_results import player_numbers, public_results
from wows_replay_analysis.process.raw_loader import RawMatch
from wows_replay_analysis.process.raw_loader import own_entity_ids

logger = logging.getLogger(__name__)


def replay_end(raw: RawMatch) -> dict:
    """Describe how the replay ended.

    Return {"replay_complete": bool, "end_reason": str, "recorded_s": float | None}.

    replay_complete is True when the replay contains the battle result
    (report hidden.battle_result with a winner, or a battle-end event in the
    timeline). Otherwise end_reason is:
      "left_after_death"  the recording player's ship was destroyed before
                          the recording stops (the usual case),
      "disconnected"      the recording player's ship was still alive at the
                          end of the recording,
      "unknown"           not enough data to tell.
    For complete replays end_reason is "battle_end".
    recorded_s is the battle time of the last timeline event (or the report
    duration when there is no timeline).
    """
    report = raw.report if isinstance(raw.report, dict) else {}
    hidden = report.get("hidden") if isinstance(report.get("hidden"), dict) else {}
    battle_result = hidden.get("battle_result")
    winner = battle_result.get("winner_team_id") if isinstance(battle_result, dict) else None
    timeline = raw.timeline if isinstance(raw.timeline, dict) else None
    events = timeline.get("events") if timeline else None
    has_battle_end = isinstance(events, list) and any(
        isinstance(event, dict) and event.get("event_type") == "BattleEndEvent"
        for event in events
    )
    complete = (
        isinstance(winner, int) and not isinstance(winner, bool)
    ) or has_battle_end

    timestamps = [
        float(event["timestamp"])
        for event in events or []
        if isinstance(event, dict)
        and isinstance(event.get("timestamp"), (int, float))
        and not isinstance(event.get("timestamp"), bool)
    ] if isinstance(events, list) else []
    start_s = battle_start_s(timeline)
    if timestamps:
        recorded_s = battle_time(max(timestamps), start_s)
    elif timeline is None:
        opened = report.get("open") if isinstance(report.get("open"), dict) else {}
        recorded_s = _number(
            opened.get("battleDuration", opened.get("duration")),
            "report duration",
            optional=True,
        )
    else:
        recorded_s = None

    if complete:
        end_reason = "battle_end"
    else:
        ship_id, own_player = _recording_player(raw, hidden)
        alive = _timeline_alive(timeline, ship_id)
        if alive is None and own_player is not None:
            alive = _boolean(own_player.get("isAlive"), "recording player's alive state")
        end_reason = (
            "left_after_death" if alive is False
            else "disconnected" if alive is True
            else "unknown"
        )
    return {
        "replay_complete": complete,
        "end_reason": end_reason,
        "recorded_s": recorded_s,
    }


def match_stats_row(raw: RawMatch) -> dict:
    """Return one row for the `matches` table (columns in database.SCHEMA).

    Ship name, class and tier come from the post-battle report when available;
    personal values missing from incomplete reports use timeline estimates.
    """
    if raw.report is None and raw.timeline is None:
        raise ValueError(f"Cannot build statistics for {raw.match_id}: report and timeline are missing")

    report = raw.report if isinstance(raw.report, dict) else {}
    opened = report.get("open") if isinstance(report.get("open"), dict) else {}
    hidden = report.get("hidden") if isinstance(report.get("hidden"), dict) else {}
    own_score = _own_score_row(hidden)
    ship_id, own_player = _recording_player(raw, hidden)
    if ship_id is None or own_player is None:
        raise ValueError(f"Could not identify the recording player in {raw.match_id}")

    team_id = _integer(
        own_score.get("team_id") if own_score
        else own_player.get("teamId", own_player.get("team_id")),
        "recording player's team id",
        optional=True,
    )
    result_info = hidden.get("battle_result")
    winner_team_id = _integer(
        result_info.get("winner_team_id") if isinstance(result_info, dict) else None,
        "winner team id",
        optional=True,
    )
    end = replay_end(raw)
    public_rows = public_results(raw) if end["replay_complete"] else None
    public_row = _public_player_row(public_rows, own_player)
    exact_numbers = player_numbers(public_row) if public_row is not None else {}
    result = "unknown" if not end["replay_complete"] else _battle_result(winner_team_id, team_id)
    if end["replay_complete"] and result is None:
        result = _timeline_result(raw.timeline, team_id)
    personal = _section_data(hidden, "personal_score", "summary")
    details_damage = _section_data(hidden, "details", "damage_received")
    team_play = _section_data(hidden, "details", "team_play")
    timeline_meta = raw.timeline.get("meta", {}) if raw.timeline else {}
    if not isinstance(timeline_meta, dict):
        timeline_meta = {}

    header = raw.meta.get("header") if isinstance(raw.meta.get("header"), dict) else {}
    played_at = _played_at(
        opened.get("dateTime") or header.get("dateTime"), raw.match_id
    )
    death_time = _time_of_death(raw.timeline, ship_id)
    timeline_alive = _timeline_alive(raw.timeline, ship_id)
    report_alive = _boolean(
        own_score.get("is_alive") if own_score else own_player.get(
            "isAlive", own_player.get("is_alive")
        ),
        "recording player's alive state",
    )
    survived = (
        timeline_alive if not end["replay_complete"] and timeline_alive is not None
        else report_alive if report_alive is not None
        else timeline_alive
    )
    timeline_stats = _timeline_personal_stats(raw.timeline, ship_id)
    used_timeline = not end["replay_complete"]

    def report_or_timeline(value: object, key: str) -> object:
        nonlocal used_timeline
        if not end["replay_complete"]:
            return timeline_stats.get(key)
        if value is not None:
            return value
        fallback = timeline_stats.get(key)
        if fallback is not None:
            used_timeline = True
        return fallback

    base_xp = None
    planes_killed = None
    if end["replay_complete"]:
        base_xp = (
            personal.get("base_exp")
            if personal.get("base_exp") is not None
            else own_score.get("exp") if own_score else None
        )
        planes_killed = (
            personal.get("planes_killed")
            if personal.get("planes_killed") is not None
            else own_score.get("planes_killed") if own_score
            else own_player.get("planesCount")
        )

    ship_name = (own_score.get("ship_name") if own_score else None) or (
        own_player.get("ship") or opened.get("playerVehicle")
    )

    ribbons = _section_value(hidden, "personal_score", "ribbons")
    ribbons_json = json.dumps(_ribbon_counts(ribbons), ensure_ascii=False, sort_keys=True)
    timeline_duration = timeline_meta.get("duration")
    duration = timeline_duration if timeline_duration is not None else end["recorded_s"]
    if duration is None:
        duration = opened.get("battleDuration", opened.get("duration"))
    start_s = battle_start_s(raw.timeline)
    if (
        timeline_duration is not None
        and isinstance(duration, Real)
        and not isinstance(duration, bool)
    ):
        duration = battle_time(float(duration), start_s)

    def exact_or_report(key: str, report_value: object) -> object:
        exact_value = exact_numbers.get(key)
        return exact_value if exact_value is not None else report_or_timeline(report_value, key)

    row = {
        "match_id": raw.match_id,
        "processor_version": PROCESSOR_VERSION,
        "played_at": played_at,
        "game_version": raw.meta.get("game_version") or opened.get("clientVersionFromXml")
        or header.get("clientVersionFromXml"),
        "map_name": opened.get("mapDisplayName") or opened.get("mapName")
        or hidden.get("map") or header.get("mapDisplayName") or header.get("mapName"),
        "match_group": opened.get("matchGroup"),
        "scenario": opened.get("scenario"),
        "player_name": own_player.get("name") or opened.get("playerName")
        or header.get("playerName"),
        "ship_name": ship_name,
        "ship_class": own_score.get("ship_type") if own_score else None,
        "ship_tier": _integer(
            own_score.get("ship_level") if own_score else None,
            "ship tier",
            optional=True,
        ),
        "result": result,
        "duration_s": _number(duration, "match duration", optional=True),
        "survived": None if survived is None else int(survived),
        "time_of_death_s": death_time,
        "damage": _integer(
            exact_or_report("damage", personal.get("damage")),
            "damage",
            optional=True,
        ),
        "spotting_damage": _integer(
            exact_or_report("spotting_damage", team_play.get("spotting_damage")),
            "spotting damage",
            optional=True,
        ),
        "potential_damage": _number(
            exact_or_report("potential_damage", personal.get("potential_damage")),
            "potential damage",
            optional=True,
        ),
        "damage_received": _integer(
            exact_or_report("damage_received", details_damage.get("total")),
            "damage received",
            optional=True,
        ),
        "distance_km": _number(
            exact_numbers.get("distance_km"),
            "distance",
            optional=True,
        ),
        "frags": _integer(
            exact_or_report(
                "frags",
                personal.get("frags") if personal.get("frags") is not None
                else own_score.get("frags") if own_score
                else own_player.get("fragsCount"),
            ),
            "frags",
            optional=True,
        ),
        "base_xp": _integer(
            base_xp,
            "base XP",
            optional=True,
        ),
        "planes_killed": _integer(
            planes_killed,
            "planes killed",
            optional=True,
        ),
        "capture_points": _integer(
            team_play.get("capture_points") if end["replay_complete"] else None,
            "capture points",
            optional=True,
        ),
        "defense_points": _integer(
            team_play.get("defense_points") if end["replay_complete"] else None,
            "defense points",
            optional=True,
        ),
        "ribbons_json": ribbons_json,
        "replay_complete": int(end["replay_complete"]),
        "end_reason": end["end_reason"],
        "recorded_s": end["recorded_s"],
        "stats_source": "timeline" if used_timeline else "report",
    }
    logger.debug("Built statistics row for %s", raw.match_id)
    return row


def _public_player_row(
    results: dict[str, dict] | None, player: dict
) -> dict | None:
    if results is None:
        return None
    name = player.get("name")
    if isinstance(name, str) and name in results:
        return results[name]
    account_id = _integer_id(player.get("id"))
    if account_id is None:
        return None
    return next(
        (
            row for row in results.values()
            if _integer_id(row.get("account_db_id")) == account_id
        ),
        None,
    )


def _recording_player(raw: RawMatch, hidden: dict) -> tuple[int | None, dict | None]:
    report_players = hidden.get("players")
    if isinstance(report_players, dict):
        entries = list(report_players.values())
    elif isinstance(report_players, list):
        entries = report_players
    else:
        entries = []

    avatar_id = hidden.get("player_id")
    own_player = next(
        (
            player for player in entries
            if isinstance(player, dict) and player.get("avatarId") == avatar_id
        ),
        None,
    )
    ship_id = _integer_id(own_player.get("shipId")) if own_player else None
    if ship_id is None and raw.report is not None:
        try:
            _, ship_id = own_entity_ids(raw)
        except ValueError:
            pass

    report = raw.report if isinstance(raw.report, dict) else {}
    opened = report.get("open") if isinstance(report.get("open"), dict) else {}
    header = raw.meta.get("header") if isinstance(raw.meta.get("header"), dict) else {}
    name = opened.get("playerName") or header.get("playerName")
    timeline_players = raw.timeline.get("players") if isinstance(raw.timeline, dict) else None
    timeline_players = timeline_players if isinstance(timeline_players, list) else []
    timeline_player = next(
        (
            player for player in timeline_players
            if isinstance(player, dict)
            and (
                _integer_id(player.get("entity_id")) == ship_id
                if ship_id is not None
                else isinstance(name, str) and player.get("name") == name
            )
        ),
        None,
    )
    if own_player is None and timeline_player is not None:
        own_player = {
            "name": timeline_player.get("name"),
            "team_id": timeline_player.get("team_id"),
            "ship": timeline_player.get("ship"),
        }
    elif own_player is not None and timeline_player is not None:
        own_player = {
            **timeline_player,
            **own_player,
            "team_id": own_player.get("teamId", timeline_player.get("team_id")),
        }
    if ship_id is None and timeline_player is not None:
        ship_id = _integer_id(timeline_player.get("entity_id"))
    return ship_id, own_player


def _timeline_alive(timeline: dict | None, ship_id: int | None) -> bool | None:
    if not isinstance(timeline, dict) or ship_id is None:
        return None
    events = timeline.get("events")
    if isinstance(events, list) and any(
        isinstance(event, dict)
        and event.get("event_type") == "DeathEvent"
        and _integer_id(event.get("victim_id", event.get("entity_id"))) == ship_id
        for event in events
    ):
        return False
    snapshots = timeline.get("state_snapshots")
    if not isinstance(snapshots, list):
        return None
    for snapshot in reversed(snapshots):
        ships = snapshot.get("ships") if isinstance(snapshot, dict) else None
        state = ships.get(str(ship_id), ships.get(ship_id)) if isinstance(ships, dict) else None
        if not isinstance(state, dict):
            continue
        alive = state.get("is_alive")
        if isinstance(alive, bool):
            return alive
        health = state.get("health")
        if isinstance(health, Real) and not isinstance(health, bool):
            return health > 0
    return None


def _timeline_personal_stats(timeline: dict | None, ship_id: int) -> dict[str, int | float]:
    if not isinstance(timeline, dict):
        return {}
    events = timeline.get("events")
    if not isinstance(events, list):
        return {}

    damage_dealt = 0.0
    damage_received = 0.0
    frag_victims: set[int] = set()
    spotted = 0.0
    potential = 0.0
    has_damage_events = False
    has_ship_stat_events = False
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type")
        if event_type == "DamageEvent":
            damage = _number(event.get("damage"), "timeline damage", optional=True)
            if damage is None:
                continue
            has_damage_events = True
            if _integer_id(event.get("attacker_id")) == ship_id:
                damage_dealt += damage
            if _integer_id(event.get("target_id", event.get("entity_id"))) == ship_id:
                damage_received += damage
        elif event_type == "DeathEvent":
            if _integer_id(event.get("killer_id")) == ship_id:
                victim_id = _integer_id(event.get("victim_id", event.get("entity_id")))
                if victim_id is not None:
                    frag_victims.add(victim_id)
        elif (
            event_type == "DamageReceivedStatEvent"
            and _integer_id(event.get("entity_id")) == ship_id
        ):
            stat_type = event.get("stat_type")
            delta = _number(event.get("delta_total"), "timeline damage statistic", optional=True)
            if delta is None:
                continue
            has_ship_stat_events = True
            if stat_type == "SPOT":
                spotted += delta
            elif stat_type == "AGRO":
                potential += delta

    stats: dict[str, int | float] = {"frags": len(frag_victims)}
    if has_damage_events:
        stats.update({
            "damage": int(round(damage_dealt)),
            "damage_received": int(round(damage_received)),
        })
    if has_ship_stat_events:
        stats.update({
            "spotting_damage": int(round(spotted)),
            "potential_damage": round(potential, 1),
        })
    return stats


def _timeline_result(timeline: dict | None, own_team: int | None) -> str | None:
    if not isinstance(timeline, dict) or own_team is None:
        return None
    snapshots = timeline.get("state_snapshots")
    if not isinstance(snapshots, list):
        return None
    for snapshot in reversed(snapshots):
        battle = snapshot.get("battle") if isinstance(snapshot, dict) else None
        scores = battle.get("team_scores") if isinstance(battle, dict) else None
        if not isinstance(scores, dict):
            continue
        parsed = {
            team: _number(score, "team score", optional=True)
            for key, score in scores.items()
            if (team := _integer_id(key)) is not None
        }
        parsed = {team: score for team, score in parsed.items() if score is not None}
        if own_team not in parsed or len(parsed) < 2:
            continue
        highest = max(parsed.values())
        winners = [team for team, score in parsed.items() if score == highest]
        if len(winners) != 1:
            return "draw"
        return "win" if winners[0] == own_team else "loss"
    return None


def _section_data(hidden: dict, tab_name: str, section_name: str) -> dict:
    data = _section_value(hidden, tab_name, section_name)
    return data if isinstance(data, dict) else {}


def _section_value(hidden: dict, tab_name: str, section_name: str) -> object:
    beta = hidden.get("battle_results_beta")
    tabs = beta.get("tabs") if isinstance(beta, dict) else None
    tab = tabs.get(tab_name) if isinstance(tabs, dict) else None
    sections = tab.get("sections") if isinstance(tab, dict) else None
    section = sections.get(section_name) if isinstance(sections, dict) else None
    return section.get("data") if isinstance(section, dict) else None


def _own_score_row(hidden: dict) -> dict | None:
    beta = hidden.get("battle_results_beta")
    tabs = beta.get("tabs") if isinstance(beta, dict) else None
    team_score = tabs.get("team_score") if isinstance(tabs, dict) else None
    sections = team_score.get("sections") if isinstance(team_score, dict) else None
    if not isinstance(sections, dict):
        return None
    for section in sections.values():
        rows = section.get("data") if isinstance(section, dict) else None
        if isinstance(rows, list):
            own = next(
                (row for row in rows if isinstance(row, dict) and row.get("is_own")),
                None,
            )
            if own is not None:
                return own
    return None


def _played_at(value: object, match_id: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Missing replay dateTime for {match_id}")
    try:
        return datetime.strptime(value, "%d.%m.%Y %H:%M:%S").isoformat(sep=" ")
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value).isoformat(sep=" ")
    except ValueError as exc:
        raise ValueError(f"Invalid replay dateTime {value!r} for {match_id}") from exc


def _integer(value: object, label: str, *, optional: bool) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _integer_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _number(value: object, label: str, *, optional: bool) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"Invalid {label}: {value!r}")
    return float(value)


def _boolean(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _battle_result(winner_team_id: int | None, own_team_id: int | None) -> str | None:
    if winner_team_id is None or winner_team_id < 0:
        return "draw" if winner_team_id is not None else None
    if own_team_id is None:
        return None
    return "win" if winner_team_id == own_team_id else "loss"


def _time_of_death(timeline: dict | None, ship_id: int) -> float | None:
    if timeline is None:
        return None
    events = timeline.get("events", [])
    if not isinstance(events, list):
        return None
    times = [
        event["timestamp"]
        for event in events
        if isinstance(event, dict)
        and event.get("event_type") == "DeathEvent"
        and (event.get("victim_id", event.get("entity_id")) == ship_id)
        and isinstance(event.get("timestamp"), (int, float))
        and not isinstance(event.get("timestamp"), bool)
    ]
    if not times:
        return None
    return battle_time(float(min(times)), battle_start_s(timeline))


def _ribbon_counts(value: object) -> dict[str, int]:
    if not isinstance(value, list):
        return {}
    result: dict[str, int] = {}
    for ribbon in value:
        if not isinstance(ribbon, dict):
            continue
        name = ribbon.get("name")
        count = ribbon.get("count")
        if isinstance(name, str) and isinstance(count, int) and not isinstance(count, bool):
            result[name] = result.get(name, 0) + count
    return result

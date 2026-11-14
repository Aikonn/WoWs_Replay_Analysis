"""Turns one raw extract into the database row for the multi-match statistics.

Built from the post-battle report (report.json); the timeline is only needed
for values the report does not have (e.g. time of death).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from numbers import Real

from wows_replay_analysis.process import PROCESSOR_VERSION
from wows_replay_analysis.process.raw_loader import RawMatch
from wows_replay_analysis.process.raw_loader import own_entity_ids

logger = logging.getLogger(__name__)


def match_stats_row(raw: RawMatch) -> dict:
    """Return one row for the `matches` table (columns in database.SCHEMA).

    Ship name, class and tier come from the post-battle report
    (battle_results_beta -> team_score), so GameParams is not needed.
    """
    if raw.report is None:
        raise ValueError(f"Cannot build statistics for {raw.match_id}: report is missing")

    report = raw.report
    opened = _object(report.get("open"), "report.open")
    hidden = _object(report.get("hidden"), "report.hidden")
    players = _object(hidden.get("players"), "report.hidden.players")
    avatar_id, ship_id = own_entity_ids(raw)
    own_player = next(
        (
            player for player in players.values()
            if isinstance(player, dict) and player.get("avatarId") == avatar_id
        ),
        None,
    )
    if own_player is None:
        raise ValueError(f"Recording player {avatar_id} is missing from {raw.match_id}")

    own_score = _own_score_row(hidden)
    team_id = _integer(
        own_score.get("team_id") if own_score else own_player.get("teamId"),
        "recording player's team id",
        optional=True,
    )
    winner_team_id = _integer(
        _object(hidden.get("battle_result"), "report.hidden.battle_result").get(
            "winner_team_id"
        ),
        "winner team id",
        optional=True,
    )
    result = _battle_result(winner_team_id, team_id)

    personal = _section_data(hidden, "personal_score", "summary")
    details_damage = _section_data(hidden, "details", "damage_received")
    team_play = _section_data(hidden, "details", "team_play")
    timeline_meta = raw.timeline.get("meta", {}) if raw.timeline else {}
    if not isinstance(timeline_meta, dict):
        timeline_meta = {}

    played_at = _played_at(opened.get("dateTime"), raw.match_id)
    death_time = _time_of_death(raw.timeline, ship_id)
    survived = _boolean(
        own_score.get("is_alive") if own_score else own_player.get("isAlive"),
        "recording player's alive state",
    )
    ship_name = (
        own_score.get("ship_name") if own_score else None
    ) or opened.get("playerVehicle")

    ribbons = _section_value(hidden, "personal_score", "ribbons")
    ribbons_json = json.dumps(_ribbon_counts(ribbons), ensure_ascii=False, sort_keys=True)

    row = {
        "match_id": raw.match_id,
        "processor_version": PROCESSOR_VERSION,
        "played_at": played_at,
        "game_version": raw.meta.get("game_version") or opened.get("clientVersionFromXml"),
        "map_name": opened.get("mapDisplayName") or opened.get("mapName") or hidden.get("map"),
        "match_group": opened.get("matchGroup"),
        "scenario": opened.get("scenario"),
        "player_name": own_player.get("name") or opened.get("playerName"),
        "ship_name": ship_name,
        "ship_class": own_score.get("ship_type") if own_score else None,
        "ship_tier": _integer(
            own_score.get("ship_level") if own_score else None,
            "ship tier",
            optional=True,
        ),
        "result": result,
        "duration_s": _number(
            timeline_meta.get("duration")
            if timeline_meta.get("duration") is not None
            else opened.get("battleDuration", opened.get("duration")),
            "match duration",
            optional=True,
        ),
        "survived": None if survived is None else int(survived),
        "time_of_death_s": death_time,
        "damage": _integer(personal.get("damage"), "damage", optional=True),
        "frags": _integer(
            personal.get("frags") if personal.get("frags") is not None
            else own_score.get("frags") if own_score else own_player.get("fragsCount"),
            "frags",
            optional=True,
        ),
        "spotting_damage": _integer(
            team_play.get("spotting_damage"), "spotting damage", optional=True
        ),
        "potential_damage": _number(
            personal.get("potential_damage"), "potential damage", optional=True
        ),
        "damage_received": _integer(
            details_damage.get("total"), "damage received", optional=True
        ),
        "base_xp": _integer(
            personal.get("base_exp") if personal.get("base_exp") is not None
            else own_score.get("exp") if own_score else None,
            "base XP",
            optional=True,
        ),
        "planes_killed": _integer(
            personal.get("planes_killed") if personal.get("planes_killed") is not None
            else own_score.get("planes_killed") if own_score else own_player.get("planesCount"),
            "planes killed",
            optional=True,
        ),
        "capture_points": _integer(
            team_play.get("capture_points"), "capture points", optional=True
        ),
        "defense_points": _integer(
            team_play.get("defense_points"), "defense points", optional=True
        ),
        "ribbons_json": ribbons_json,
    }
    logger.debug("Built statistics row for %s", raw.match_id)
    return row


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {label}")
    return value


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
    return float(min(times)) if times else None


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

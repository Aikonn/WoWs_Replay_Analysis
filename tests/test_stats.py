from __future__ import annotations

import json

import pytest

from wows_replay_analysis.process import PROCESSOR_VERSION
from wows_replay_analysis.process.raw_loader import RawMatch
from wows_replay_analysis.process.stats import match_stats_row, replay_end


def make_raw(*, timeline: dict | None = None) -> RawMatch:
    report = {
        "open": {
            "dateTime": "13.11.2026 18:42:44",
            "mapDisplayName": "Shards",
            "matchGroup": "pvp",
            "scenario": "domination_3point",
            "clientVersionFromXml": "15,10,0,13533378",
            "playerName": "Captain",
            "playerVehicle": "ShipCode",
            "battleDuration": 1200,
        },
        "hidden": {
            "player_id": 100,
            "players": {
                "account": {
                    "avatarId": 100,
                    "shipId": 200,
                    "name": "Captain",
                    "teamId": 0,
                    "isAlive": False,
                    "fragsCount": 2,
                    "planesCount": 3,
                }
            },
            "battle_result": {"winner_team_id": 1},
            "battle_results_beta": {
                "tabs": {
                    "team_score": {
                        "sections": {
                            "allies": {
                                "data": [
                                    {
                                        "is_own": True,
                                        "team_id": 0,
                                        "is_alive": False,
                                        "ship_name": "Ship Name",
                                        "ship_type": "Cruiser",
                                        "ship_level": 8,
                                        "frags": 2,
                                        "planes_killed": 3,
                                        "exp": 1400,
                                    }
                                ]
                            }
                        }
                    },
                    "personal_score": {
                        "sections": {
                            "summary": {
                                "data": {
                                    "damage": 40000,
                                    "frags": 2,
                                    "planes_killed": 3,
                                    "base_exp": 1400,
                                    "potential_damage": 250000.5,
                                    "capture_points": 12,
                                    "defense_points": 4,
                                }
                            },
                            "ribbons": {
                                "data": [
                                    {"name": "RIBBON_HIT", "count": 5},
                                    {"name": "RIBBON_HIT", "count": 2},
                                    {"name": "RIBBON_FRAG", "count": 1},
                                ]
                            },
                        }
                    },
                    "details": {
                        "sections": {
                            "damage_received": {"data": {"total": 12000}},
                            "team_play": {
                                "data": {
                                    "spotting_damage": 6000,
                                    "capture_points": 12,
                                    "defense_points": 4,
                                }
                            },
                        }
                    },
                }
            },
        },
    }
    return RawMatch(
        match_id="match",
        meta={"game_version": "15,10,0,13533378"},
        report=report,
        timeline=timeline,
    )


def test_match_stats_row_maps_report_and_timeline_fields() -> None:
    raw = make_raw(
        timeline={
            "meta": {"duration": 802.5},
            "events": [
                {"event_type": "DeathEvent", "victim_id": 999, "timestamp": 10.0},
                {"event_type": "DeathEvent", "victim_id": 200, "timestamp": 600.25},
            ],
        }
    )

    row = match_stats_row(raw)

    assert row == {
        "match_id": "match",
        "processor_version": PROCESSOR_VERSION,
        "played_at": "2026-11-13 18:42:44",
        "game_version": "15,10,0,13533378",
        "map_name": "Shards",
        "match_group": "pvp",
        "scenario": "domination_3point",
        "player_name": "Captain",
        "ship_name": "Ship Name",
        "ship_class": "Cruiser",
        "ship_tier": 8,
        "result": "loss",
        "duration_s": 802.5,
        "survived": 0,
        "time_of_death_s": 600.25,
        "damage": 40000,
        "frags": 2,
        "spotting_damage": 6000,
        "potential_damage": 250000.5,
        "damage_received": 12000,
        "base_xp": 1400,
        "planes_killed": 3,
        "capture_points": 12,
        "defense_points": 4,
        "ribbons_json": json.dumps(
            {"RIBBON_FRAG": 1, "RIBBON_HIT": 7}, sort_keys=True
        ),
        "replay_complete": 1,
        "end_reason": "battle_end",
        "recorded_s": 600.25,
        "stats_source": "report",
    }


def test_match_stats_row_uses_report_duration_without_timeline() -> None:
    row = match_stats_row(make_raw())

    assert row["duration_s"] == 1200.0
    assert row["time_of_death_s"] is None
    assert row["recorded_s"] == 1200.0


def test_match_stats_row_requires_report_or_timeline() -> None:
    with pytest.raises(ValueError, match="report and timeline are missing"):
        match_stats_row(RawMatch("match", {}, None, None))


def test_replay_end_detects_complete_report_and_records_last_event_time() -> None:
    raw = make_raw(
        timeline={
            "events": [
                {"event_type": "PositionEvent", "timestamp": 10.0},
                {"event_type": "BattleEndEvent", "timestamp": 600.5},
            ]
        }
    )

    assert replay_end(raw) == {
        "replay_complete": True,
        "end_reason": "battle_end",
        "recorded_s": 600.5,
    }


def test_replay_end_distinguishes_left_after_death_and_disconnected() -> None:
    report = make_raw().report
    assert report is not None
    report["hidden"].pop("battle_result")
    timeline = {
        "events": [
            {"event_type": "DeathEvent", "victim_id": 200, "timestamp": 90.0},
        ],
        "state_snapshots": [
            {"ships": {"200": {"is_alive": False, "health": 0}}}
        ],
    }
    raw = make_raw(timeline=timeline)
    raw.report = report
    assert replay_end(raw)["end_reason"] == "left_after_death"

    report["hidden"]["players"]["account"]["isAlive"] = True
    timeline["events"] = []
    timeline["state_snapshots"] = [
        {"ships": {"200": {"is_alive": True, "health": 1}}}
    ]
    assert replay_end(raw)["end_reason"] == "disconnected"


def test_incomplete_match_stats_fall_back_to_timeline() -> None:
    report = make_raw().report
    assert report is not None
    report["hidden"].pop("battle_result")
    report["hidden"].pop("battle_results_beta")
    raw = make_raw(
        timeline={
            "meta": {"duration": 100.0},
            "events": [
                {
                    "event_type": "DamageEvent",
                    "attacker_id": 200,
                    "target_id": 300,
                    "damage": 125,
                },
                {
                    "event_type": "DamageEvent",
                    "attacker_id": 300,
                    "target_id": 200,
                    "damage": 75,
                },
                {"event_type": "DeathEvent", "victim_id": 200, "killer_id": 300, "timestamp": 90},
                {"event_type": "DeathEvent", "victim_id": 301, "killer_id": 200, "timestamp": 80},
                {"event_type": "DeathEvent", "victim_id": 301, "killer_id": 200, "timestamp": 80},
                {
                    "event_type": "DamageReceivedStatEvent",
                    "entity_id": 200,
                    "stat_type": "SPOT",
                    "delta_total": 30,
                },
                {
                    "event_type": "DamageReceivedStatEvent",
                    "entity_id": 200,
                    "stat_type": "AGRO",
                    "delta_total": 1000,
                },
            ],
            "state_snapshots": [
                {"ships": {"200": {"is_alive": False, "health": 0}}}
            ],
        }
    )
    raw.report = report

    row = match_stats_row(raw)

    assert row["result"] == "unknown"
    assert row["replay_complete"] == 0
    assert row["end_reason"] == "left_after_death"
    assert row["recorded_s"] == 90.0
    assert row["duration_s"] == 100.0
    assert row["damage"] == 125
    assert row["damage_received"] == 75
    assert row["frags"] == 1
    assert row["spotting_damage"] == 30
    assert row["potential_damage"] == 1000.0
    assert row["stats_source"] == "timeline"

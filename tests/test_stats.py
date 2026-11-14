from __future__ import annotations

import json

import pytest

from wows_replay_analysis.process import PROCESSOR_VERSION
from wows_replay_analysis.process.raw_loader import RawMatch
from wows_replay_analysis.process.stats import match_stats_row


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
    }


def test_match_stats_row_uses_report_duration_without_timeline() -> None:
    row = match_stats_row(make_raw())

    assert row["duration_s"] == 1200.0
    assert row["time_of_death_s"] is None


def test_match_stats_row_requires_report() -> None:
    with pytest.raises(ValueError, match="report is missing"):
        match_stats_row(RawMatch("match", {}, None, None))

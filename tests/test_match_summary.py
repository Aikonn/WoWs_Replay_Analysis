from __future__ import annotations

import json
from pathlib import Path

import pytest

from wows_replay_analysis.config import Config
from wows_replay_analysis.process import PROCESSOR_VERSION
from wows_replay_analysis.process import match_summary as match_summary_module
from wows_replay_analysis.process import stats as stats_module
from wows_replay_analysis.process.match_summary import (
    build_all_summaries,
    build_match_summary,
    decided_by,
    readable_ship_name,
    write_match_summary,
)
from wows_replay_analysis.process.raw_loader import RawMatch


def report_data() -> dict:
    return {
        "open": {
            "dateTime": "13.11.2026 18:42:44",
            "mapDisplayName": "Shards",
            "matchGroup": "pvp",
            "scenario": "domination_3point",
            "clientVersionFromXml": "15,10,0,13533378",
            "playerName": "Captain",
            "playerVehicle": "ShipCode",
            "battleDuration": 120,
        },
        "hidden": {
            "player_id": 100,
            "players": {
                "1": {
                    "id": 1,
                    "avatarId": 100,
                    "shipId": 200,
                    "name": "Captain",
                    "teamId": 0,
                    "isAlive": False,
                },
                "2": {
                    "id": 2,
                    "avatarId": 101,
                    "shipId": 300,
                    "name": "Enemy",
                    "teamId": 1,
                    "isAlive": True,
                },
            },
            "battle_result": {"winner_team_id": 1, "victory_type": 2},
            "death_info": {"200": {"killer_id": 300, "name": "TORPEDO"}},
            "shots_damage_map": {"200": {"300": 100}, "300": {"200": 50}},
            "battle_results_beta": {
                "tabs": {
                    "team_score": {
                        "sections": {
                            "allies": {
                                "data": [
                                    {
                                        "username": "Captain",
                                        "is_own": True,
                                        "team_id": 0,
                                        "ship_name": "Ship Name",
                                        "ship_type": "Cruiser",
                                        "ship_level": 8,
                                        "is_alive": False,
                                        "frags": 1,
                                        "exp": 1400,
                                    }
                                ]
                            },
                            "enemies": {
                                "data": [
                                    {
                                        "username": "Enemy",
                                        "team_id": 1,
                                        "ship_name": "Enemy Ship",
                                        "ship_type": "Battleship",
                                        "ship_level": 10,
                                        "is_alive": True,
                                        "frags": 2,
                                        "exp": 1500,
                                    }
                                ]
                            },
                        }
                    },
                    "personal_score": {
                        "sections": {
                            "summary": {
                                "data": {
                                    "damage": 100,
                                    "frags": 1,
                                    "planes_killed": 0,
                                    "base_exp": 1400,
                                    "potential_damage": 250.0,
                                    "capture_points": 2,
                                    "defense_points": 3,
                                }
                            },
                            "ribbons": {
                                "data": [{"name": "RIBBON_HIT", "count": 4}]
                            },
                        }
                    },
                    "details": {
                        "sections": {
                            "damage_to_ships": {
                                "data": {"total": 100, "torpedoes": {"damage": 100}}
                            },
                            "damage_received": {
                                "data": {"total": 50, "torpedoes": {"damage": 50}}
                            },
                            "team_play": {
                                "data": {"spotting_damage": 12}
                            },
                        }
                    },
                }
            },
        },
    }


def timeline_data() -> dict:
    return {
        "meta": {"duration": 60, "snapshot_interval": 30},
        "players": [
            {
                "name": "Captain", "entity_id": 200, "account_id": 1,
                "team_id": 0, "ship_id": 7001, "max_health": 10,
            },
            {
                "name": "Enemy", "entity_id": 300, "account_id": 2,
                "team_id": 1, "ship_id": 7002, "max_health": 10,
            },
        ],
        "state_snapshots": [
            {
                "timestamp": timestamp,
                "ships": {
                    "200": {
                        "position": [0, 0, 0],
                        "yaw": 1.5,
                        "health": 10 if timestamp == 0 else 0,
                        "max_health": 10,
                        "is_alive": timestamp == 0,
                    },
                    "300": {
                        "position": [3, 0, 4],
                        "is_detected": True,
                    },
                },
                "battle": {"team_scores": {"0": timestamp, "1": 60 - timestamp}},
            }
            for timestamp in (0, 30, 60)
        ],
        "events": [
            {
                "event_type": "DamageEvent",
                "timestamp": 10,
                "attacker_id": 200,
                "target_id": 300,
                "damage": 40,
            },
            {
                "event_type": "DamageEvent",
                "timestamp": 20,
                "attacker_id": 300,
                "target_id": 200,
                "damage": 50,
            },
            {
                "event_type": "ConsumableEvent",
                "timestamp": 20,
                "vehicle_id": 200,
                "is_used": True,
                "consumable_id": 1,
                "consumable_type": 2,
                "work_time_left": 5.0,
            },
            {
                "event_type": "CapturePointUpdateEvent",
                "timestamp": 25,
                "zone_entity_id": 500,
                "team_id": 0,
                "progress": 0.5,
            },
            {
                "event_type": "ChatEvent",
                "timestamp": 30,
                "sender_id": 2,
                "channel": "battle_team",
                "message": "Good luck",
            },
            {
                "event_type": "DeathEvent",
                "timestamp": 45,
                "victim_id": 200,
                "killer_id": 300,
            },
        ],
    }


def make_raw(*, report: dict | None = None, timeline: dict | None = None) -> RawMatch:
    return RawMatch(
        "match",
        {
            "game_version": "15,10,0,13533378",
            "header": {
                "dateTime": "13.11.2026 18:42:44",
                "playerName": "Captain",
                "mapName": "spaces/23_Shards",
            },
        },
        report,
        timeline,
    )


def test_build_match_summary_combines_report_and_timeline_compactly() -> None:
    timeline = timeline_data()
    timeline["players"][1]["ship"] = "PHSB710_Willem_de_Eerste"
    summary = build_match_summary(make_raw(report=report_data(), timeline=timeline))

    assert summary["processor_version"] == PROCESSOR_VERSION
    assert summary["match"]["result"] == "loss"
    assert summary["match"]["decided_by"] == "all_allies_destroyed"
    assert summary["match"]["map"] == "Shards"
    assert summary["me"]["player"] == "Captain"
    assert summary["me"]["ship"] == {
        "name": "Ship Name",
        "ship_id": "Ship Name",
        "class": "Cruiser",
        "tier": 8,
    }
    assert summary["me"]["killed_by"]["weapon"] == "TORPEDO"
    assert summary["me"]["ribbons"] == {"RIBBON_HIT": 4}
    assert "damage" not in summary["teams"]["allies"][0]
    assert "damage_timeline" not in summary["teams"]["enemies"][0]
    assert "damage" not in summary["teams"]["enemies"][0]
    assert summary["teams"]["enemies"][0]["ship_id"] == "Enemy Ship"
    assert [sample["time_s"] for sample in summary["timeline"]] == [0, 30, 60]
    assert summary["timeline"][0]["nearest_enemies"][0]["distance_km"] == 0.2
    assert summary["timeline"][0]["nearest_enemies"][0]["ship"] == "Willem de Eerste"
    assert summary["timeline"][0]["heading"] == 86
    assert "max_health" not in summary["timeline"][0]
    assert summary["me"]["max_health"] == 10
    assert {event["type"] for event in summary["events"]} == {
        "damage_summary",
        "consumable",
        "capture_point",
        "team_chat",
        "kill",
    }
    consumable = next(
        event for event in summary["events"] if event["type"] == "consumable"
    )
    assert consumable == {
        "type": "consumable",
        "time_s": 20.0,
        "consumable": "airDefenseDisp",
        "duration_s": 5.0,
    }
    assert len(json.dumps(summary).encode("utf-8")) < 50_000


def test_build_match_summary_uses_public_numbers_for_every_player(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {
        "Captain": {
            "name": "Captain",
            "damage": 81673,
            "scouting_damage": 39511,
            "agro_art": 192900.0,
            "agro_tpd": 92330.0,
            "ships_killed": 1,
            "life_time_sec": 694,
            "distance": 58.38245141185819,
            "received_damage_adbomb": 5781,
            "received_damage_dbomb_airsupport": 5781,
        },
        "Enemy": {
            "name": "Enemy",
            "damage": 100000,
            "scouting_damage": 20000,
            "agro_art": 200000.0,
            "ships_killed": 2,
            "life_time_sec": 700,
            "distance": 20.125,
            "received_damage_main_he": 1234,
        },
    }
    monkeypatch.setattr(stats_module, "public_results", lambda _: rows)
    monkeypatch.setattr(match_summary_module, "public_results", lambda _: rows)

    summary = build_match_summary(make_raw(report=report_data(), timeline=timeline_data()))

    assert summary["me"]["damage"] == 81673
    assert summary["me"]["damage_received"] == 5781
    assert summary["me"]["damage_received_by_type"] == {
        "total": 5781,
        "dbomb_airsupport": 5781,
    }
    assert summary["me"]["spotting_damage"] == 39511
    assert summary["me"]["potential_damage"] == 285230
    assert summary["me"]["life_time_s"] == 694
    assert summary["me"]["distance_km"] == 58.38
    assert summary["teams"]["enemies"][0]["damage"] == 100000
    assert summary["teams"]["enemies"][0]["damage_received"] == 1234
    assert summary["teams"]["enemies"][0]["distance_km"] == 20.12


def test_build_match_summary_converts_timeline_times_to_battle_time() -> None:
    timeline = timeline_data()
    start_s = 32.35
    timeline["meta"]["duration"] += start_s
    for snapshot in timeline["state_snapshots"]:
        snapshot["timestamp"] += start_s
    for event in timeline["events"]:
        event["timestamp"] += start_s
    timeline["events"].append(
        {"event_type": "BattleResultsEvent", "timestamp": start_s + 60.0}
    )
    timeline["events"][:0] = [
        {
            "event_type": "PropertyUpdateEvent",
            "entity_type": "BattleLogic",
            "property_name": "timeLeft",
            "value": 0,
            "timestamp": 31.4,
        },
        {
            "event_type": "PropertyUpdateEvent",
            "entity_type": "BattleLogic",
            "property_name": "timeLeft",
            "value": 1200,
            "timestamp": start_s,
        },
    ]

    summary = build_match_summary(make_raw(report=report_data(), timeline=timeline))

    assert summary["match"]["battle_start_s"] == start_s
    assert summary["match"]["duration_s"] == 60.0
    assert summary["match"]["recorded_s"] == 60.0
    assert summary["match"]["time_note"] == (
        "Times are seconds since battle start. In-game clock = 20:00 minus the time."
    )
    assert summary["me"]["time_of_death_s"] == 45.0
    assert [sample["time_s"] for sample in summary["timeline"]] == [0, 30, 60]
    assert next(event for event in summary["events"] if event["type"] == "kill")["time_s"] == 45.0


def test_build_match_summary_is_useful_without_timeline() -> None:
    summary = build_match_summary(make_raw(report=report_data()))

    assert summary["me"]["damage"] == 100
    assert summary["teams"]["allies"][0]["player"] == "Captain"
    assert summary["timeline"] == []
    assert summary["events"] == []


def test_build_match_summary_is_useful_without_report() -> None:
    summary = build_match_summary(make_raw(timeline=timeline_data()))

    assert summary["match"]["map"] == "23_Shards"
    assert summary["match"]["result"] == "unknown"
    assert summary["match"]["replay_complete"] == 0
    assert summary["match"]["end_reason"] == "left_after_death"
    assert summary["match"]["recorded_s"] == 45.0
    assert summary["match"]["note"] == "Events after recorded_s are unknown."
    assert summary["me"]["player"] == "Captain"
    assert summary["me"]["damage"] == 40
    assert summary["me"]["damage_received"] is None
    assert summary["me"]["survived"] is False
    assert summary["me"]["stats_source"] == "timeline"
    assert summary["teams"]["enemies"][0]["player"] == "Enemy"
    assert summary["timeline"]


def test_incomplete_teams_get_ship_details_from_gamedata(tmp_path: Path) -> None:
    data_dir = tmp_path / "gamedata"
    (data_dir / "data").mkdir(parents=True)
    (data_dir / "data" / "ships.json").write_text(
        json.dumps({
            "7001": {"name": "PRSS110_K_type", "level": 10, "species": "Battleship"},
            "7002": {"name": "PGSS510_U4501", "level": 10, "species": "Submarine"},
            "7003": {"name": "PRSS110_Fallback_ship", "level": 8, "species": "Cruiser"},
        }),
        encoding="utf-8",
    )
    (data_dir / "data" / "ship_names.json").write_text(
        json.dumps({"7001": "K-1", "7002": "U-4501"}),
        encoding="utf-8",
    )

    timeline = timeline_data()
    timeline["players"].append({
        "name": "Fallback",
        "entity_id": 301,
        "account_id": 3,
        "team_id": 1,
        "ship_id": 7003,
        "max_health": 10,
    })
    timeline["events"][2]["work_time_left"] = 1.0499999523162842
    partial_report = {
        "open": {"playerName": "Captain", "playerVehicle": "PRSS110-K-type"},
        "hidden": {
            "player_id": 100,
            "players": {
                "1": {
                    "id": 1,
                    "avatarId": 100,
                    "shipId": 200,
                    "name": "Captain",
                    "teamId": 0,
                    "isAlive": False,
                }
            },
        },
    }
    summary = build_match_summary(
        make_raw(report=partial_report, timeline=timeline), data_dir
    )

    assert summary["me"]["ship"] == {
        "name": "K-1",
        "ship_id": "PRSS110_K_type",
        "class": "Battleship",
        "tier": 10,
    }
    assert summary["teams"]["allies"][0]["ship"] == "K-1"
    assert summary["teams"]["allies"][0]["ship_id"] == "PRSS110_K_type"
    assert summary["teams"]["allies"][0]["class"] == "Battleship"
    assert summary["teams"]["allies"][0]["tier"] == 10
    assert summary["teams"]["enemies"][0]["ship"] == "U-4501"
    fallback = next(
        player for player in summary["teams"]["enemies"]
        if player["player"] == "Fallback"
    )
    assert fallback["ship"] == "Fallback ship"
    assert summary["timeline"][0]["nearest_enemies"][0]["ship"] == "U-4501"
    assert summary["me"]["damage_received_events"][0]["attacker"]["ship"] == "U-4501"
    kill = next(event for event in summary["events"] if event["type"] == "kill")
    assert kill["killer"]["ship"] == "U-4501"
    consumable = next(event for event in summary["events"] if event["type"] == "consumable")
    assert consumable["duration_s"] == 1.0


@pytest.mark.parametrize(
    ("internal_name", "expected"),
    [
        ("PRSS110_K_type", "K type"),
        ("PGSS510_U4501", "U4501"),
        ("Unknown_ship_code", "Unknown_ship_code"),
        (None, None),
    ],
)
def test_readable_ship_name(internal_name: str | None, expected: str | None) -> None:
    assert readable_ship_name(internal_name) == expected


def test_decided_by_uses_eliminated_team_from_report() -> None:
    report = report_data()
    report["hidden"]["players"]["1"]["isAlive"] = True
    report["hidden"]["players"]["2"]["isAlive"] = False

    assert decided_by(make_raw(report=report), own_team=0) == "all_enemies_destroyed"


def test_decided_by_uses_timeline_scores_and_time_limit() -> None:
    report = report_data()
    for player in report["hidden"]["players"].values():
        player["isAlive"] = True
    timeline = {
        "meta": {"duration": 120},
        "state_snapshots": [{"battle": {"team_scores": {"0": 1000, "1": 500}}}],
    }
    assert decided_by(make_raw(report=report, timeline=timeline), own_team=0) == "points"

    timeline["state_snapshots"] = [
        {"battle": {"team_scores": {"0": 800, "1": 700}, "time_left": 0}}
    ]
    assert decided_by(make_raw(report=report, timeline=timeline), own_team=0) == "time"


def test_decided_by_is_unknown_without_battle_end_evidence() -> None:
    report = report_data()
    report["hidden"].pop("battle_result")
    assert decided_by(make_raw(report=report), own_team=0) is None


def test_write_match_summary_is_atomic_and_rejects_path_like_ids(tmp_path: Path) -> None:
    path = write_match_summary({"processor_version": 1}, tmp_path / "matches", "match")

    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == {"processor_version": 1}
    with pytest.raises(ValueError, match="Invalid match id"):
        write_match_summary({}, tmp_path, "..\\outside")


def test_build_all_summaries_skips_current_and_force_rebuilds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = Config(tmp_path, tmp_path / "data", tmp_path / "cache")
    raw_dir = config.raw_dir / "match"
    raw_dir.mkdir(parents=True)
    (raw_dir / "meta.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "wows_replay_analysis.process.match_summary.load_raw_match",
        lambda _: make_raw(report=report_data()),
    )

    assert build_all_summaries(config) == 1
    assert build_all_summaries(config) == 0
    assert build_all_summaries(config, force=True) == 1
    saved = json.loads((config.matches_dir / "match.json").read_text(encoding="utf-8"))
    assert saved["processor_version"] == PROCESSOR_VERSION


def test_build_all_summaries_loads_catalogs_once_per_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = Config(tmp_path, tmp_path / "data", tmp_path / "cache")
    for match_id in ("match-one", "match-two"):
        raw_dir = config.raw_dir / match_id
        raw_dir.mkdir(parents=True)
        (raw_dir / "meta.json").write_text("{}", encoding="utf-8")

    calls = {"ships": 0, "projectiles": 0}

    def load_ships(_: Path) -> None:
        calls["ships"] += 1
        return None

    def load_projectiles(_: Path) -> None:
        calls["projectiles"] += 1
        return None

    monkeypatch.setattr(match_summary_module, "_load_ship_catalog", load_ships)
    monkeypatch.setattr(match_summary_module, "_load_projectile_types", load_projectiles)
    monkeypatch.setattr(
        "wows_replay_analysis.process.match_summary.load_raw_match",
        lambda _: make_raw(report=report_data()),
    )

    assert build_all_summaries(config, force=True) == 2
    assert calls == {"ships": 1, "projectiles": 1}

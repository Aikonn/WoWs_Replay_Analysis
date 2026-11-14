from __future__ import annotations

from wows_replay_analysis.process.combat import (
    battle_start_s,
    battle_time,
    check_damage_consistency,
    damage_dealt_by_ship,
    damage_windows,
    deduplicate_deaths,
    healing_received,
    health_track,
    killing_blows,
    world_to_km,
)


def test_battle_start_s_finds_the_end_of_the_countdown() -> None:
    timeline = {
        "events": [
            {
                "entity_type": "BattleLogic",
                "property_name": "timeLeft",
                "value": 30,
                "timestamp": 2.3,
            },
            {
                "entity_type": "BattleLogic",
                "property_name": "timeLeft",
                "value": 0,
                "timestamp": 31.4,
            },
            {
                "entity_type": "BattleLogic",
                "property_name": "timeLeft",
                "value": 1200,
                "timestamp": 32.35,
            },
            {
                "entity_type": "BattleLogic",
                "property_name": "battleStage",
                "value": 0,
                "timestamp": 32.35,
            },
        ]
    }

    assert battle_start_s(timeline) == 32.35
    assert battle_start_s({"events": []}) is None
    assert battle_start_s(None) is None


def test_battle_time_subtracts_the_start_and_leaves_unknown_start_unchanged() -> None:
    assert battle_time(727.08, 32.35) == 694.7
    assert battle_time(12.345, None) == 12.345


def _combat_timeline() -> dict:
    return {
        "players": [
            {"entity_id": 1, "max_health": 100},
            {"entity_id": 2, "max_health": 75},
            {"entity_id": 3, "max_health": 15},
        ],
        "events": [
            {"event_type": "PropertyUpdateEvent", "entity_id": 1, "property_name": "health", "value": 80, "timestamp": 10},
            {"event_type": "PropertyUpdateEvent", "entity_id": 1, "property_name": "health", "value": 90, "timestamp": 20},
            {"event_type": "PropertyUpdateEvent", "entity_id": 1, "property_name": "health", "value": 100, "timestamp": 21},
            {"event_type": "PropertyUpdateEvent", "entity_id": 1, "property_name": "health", "value": 95, "timestamp": 22},
            {"event_type": "PropertyUpdateEvent", "entity_id": 1, "property_name": "health", "value": 100, "timestamp": 23},
            {"event_type": "PropertyUpdateEvent", "entity_id": 1, "property_name": "health", "value": 50, "timestamp": 40},
            {"event_type": "PropertyUpdateEvent", "entity_id": 1, "property_name": "health", "value": 0, "timestamp": 65},
            {"event_type": "PropertyUpdateEvent", "entity_id": 1, "property_name": "regeneratedHealth", "value": 25, "timestamp": 23},
            {"event_type": "PropertyUpdateEvent", "entity_id": 2, "property_name": "health", "value": 75, "timestamp": 1},
            {"event_type": "PropertyUpdateEvent", "entity_id": 3, "property_name": "health", "value": 15, "timestamp": 49},
            {"event_type": "DamageEvent", "attacker_id": 1, "target_id": 2, "damage": 25, "timestamp": 15},
            {"event_type": "DamageEvent", "attacker_id": 0, "target_id": 1, "damage": 5, "timestamp": 16},
            {"event_type": "DeathEvent", "entity_id": 3, "victim_id": 3, "killer_id": 1, "death_reason": 0, "timestamp": 50},
            {"event_type": "DeathEvent", "entity_id": 99, "victim_id": 3, "killer_id": 1, "death_reason": 4, "timestamp": 50},
            {"event_type": "DeathEvent", "entity_id": 1, "victim_id": 1, "killer_id": 2, "death_reason": 3, "timestamp": 65},
        ],
    }


def test_world_to_km_uses_30_metre_world_units() -> None:
    assert world_to_km(100) == 3.0
    assert world_to_km(5) == 0.2


def test_health_track_seeds_max_health_and_drops_repeats() -> None:
    assert health_track(_combat_timeline(), 1) == [
        (0.0, 100.0),
        (10.0, 80.0),
        (20.0, 90.0),
        (21.0, 100.0),
        (22.0, 95.0),
        (23.0, 100.0),
        (40.0, 50.0),
        (65.0, 0.0),
    ]


def test_deduplicate_deaths_keeps_avatar_message_and_original_order() -> None:
    deaths = deduplicate_deaths(_combat_timeline()["events"])

    assert [(event["victim_id"], event["death_reason"]) for event in deaths] == [
        (3, 4),
        (1, 3),
    ]


def test_killing_blows_uses_last_positive_hp_and_snapshot_fallback() -> None:
    timeline = _combat_timeline()
    timeline["state_snapshots"] = [
        {"timestamp": 19, "ships": {"4": {"health": 300}}}
    ]
    timeline["events"].append(
        {"event_type": "DeathEvent", "entity_id": 900, "victim_id": 4, "killer_id": 1, "timestamp": 20}
    )

    blows = killing_blows(timeline)

    assert [(row["victim_id"], row["damage"]) for row in blows] == [
        (3, 15.0),
        (1, 50.0),
        (4, 300.0),
    ]


def test_damage_dealt_by_ship_adds_killing_blows_but_not_unknown_attackers() -> None:
    assert damage_dealt_by_ship(_combat_timeline()) == {1: 40.0, 2: 50.0}


def test_healing_received_groups_ticks_and_prefers_regenerated_health() -> None:
    healing = healing_received(_combat_timeline(), 1)

    assert healing == {
        "total": 25.0,
        "events": [
            {"start_s": 20.0, "end_s": 21.0, "amount": 20.0},
            {"start_s": 23.0, "end_s": 23.0, "amount": 5.0},
        ],
    }


def test_damage_windows_include_death_and_stop_at_its_time() -> None:
    windows = damage_windows(_combat_timeline(), 1, end_s=100)

    assert windows[-1]["end_s"] == 65.0
    assert windows[-1]["damage_taken"] == 50.0
    assert windows[-1]["damage_dealt"] == 0.0
    assert sum(window["damage_taken"] for window in windows) == 125.0
    assert sum(window["damage_dealt"] for window in windows) == 40.0
    assert sum(window["healed"] for window in windows) == 25.0
    assert all(window["start_s"] < 65 for window in windows)


def test_damage_windows_are_anchored_to_battle_time() -> None:
    timeline = _combat_timeline()
    start_s = 32.35
    for event in timeline["events"]:
        event["timestamp"] += start_s
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

    windows = damage_windows(timeline, 1, end_s=65)

    assert windows[-1]["end_s"] == 65.0
    assert windows[-1]["start_s"] == 60.0


def test_check_damage_consistency_reports_each_problem() -> None:
    summary = {
        "match": {"replay_complete": 1, "end_reason": "battle_end"},
        "me": {
            "player": "Captain",
            "damage_received": 100,
            "damage_received_by_type": {"total": 50, "main_he": 40},
            "healing": {"total": 0},
            "max_health": 200,
            "final_health": 0,
            "damage_taken_changes": 1,
            "time_of_death_s": 10,
            "life_time_s": 20,
            "frags": 3,
            "survived": False,
        },
        "events": [
            {"type": "damage_summary", "damage_taken": 50},
            {"type": "kill", "victim_id": 2, "killer": {"name": "Enemy"}},
            {"type": "kill", "victim_id": 2, "killer": {"name": "Captain"}},
            {"type": "kill", "victim_id": 3, "killer": {"name": "Captain"}},
        ],
    }

    problems = check_damage_consistency(summary)

    assert len(problems) == 6
    assert any("damage_received_by_type" in problem for problem in problems)
    assert any("minus healing" in problem for problem in problems)
    assert any("time_of_death_s" in problem for problem in problems)
    assert any("duplicate victims" in problem for problem in problems)
    assert any("me.frags" in problem for problem in problems)

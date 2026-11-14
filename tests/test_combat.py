from __future__ import annotations

from wows_replay_analysis.process.combat import battle_start_s, battle_time


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

from __future__ import annotations

import logging

from wows_replay_analysis.process import public_results as public_results_module
from wows_replay_analysis.process.raw_loader import RawMatch


def make_raw(values: dict[str, list]) -> RawMatch:
    return RawMatch(
        "match",
        {},
        None,
        {
            "events": [
                {
                    "event_type": "BattleResultsEvent",
                    "results": {"playersPublicInfo": values},
                }
            ]
        },
    )


def test_public_results_decodes_values_with_the_selected_field_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = ("account_db_id", "name", "team_id")
    raw = make_raw(
        {"1": [1, "Captain", 0], "2": [2, "Enemy", 1]},
    )
    monkeypatch.setattr(
        public_results_module, "_client_public_results_names", lambda _: names
    )

    assert public_results_module.public_results(raw) == {
        "Captain": {"account_db_id": 1, "name": "Captain", "team_id": 0},
        "Enemy": {"account_db_id": 2, "name": "Enemy", "team_id": 1},
    }


def test_public_results_returns_none_and_warns_on_field_count_mismatch(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    names = ("account_db_id", "name", "team_id")
    raw = make_raw({"1": [1, "Captain"]})
    monkeypatch.setattr(
        public_results_module, "_client_public_results_names", lambda _: names
    )

    with caplog.at_level(logging.WARNING):
        assert public_results_module.public_results(raw) is None

    assert "expected 3 values, got 2" in caplog.text


def test_received_damage_breakdown_excludes_parent_and_counts_subtypes_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    row = {
        "received_damage_bomb": 9,
        "received_damage_bomb_avia": 3,
        "received_damage_bomb_airsupport": 6,
        "received_damage_main_he": 5,
    }

    with caplog.at_level(logging.WARNING):
        breakdown = public_results_module.received_damage_breakdown(row)

    assert breakdown == {
        "total": 14,
        "bomb_avia": 3,
        "bomb_airsupport": 6,
        "main_he": 5,
    }
    assert not caplog.records


def test_received_damage_breakdown_warns_when_parent_does_not_match(
    caplog: pytest.LogCaptureFixture,
) -> None:
    row = {
        "received_damage_adbomb": 10,
        "received_damage_dbomb_airsupport": 6,
    }

    with caplog.at_level(logging.WARNING):
        breakdown = public_results_module.received_damage_breakdown(row)

    assert breakdown == {"total": 6, "dbomb_airsupport": 6}
    assert "received_damage_adbomb is 10 but its sub-types sum to 6" in caplog.text

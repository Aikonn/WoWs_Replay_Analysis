from __future__ import annotations

from types import SimpleNamespace

import pytest
import wows_replay_parser.events.models as models
import wows_replay_parser.events.stream as stream

from wows_replay_analysis.extract.parser_patches import (
    _consumable_factory,
    apply_timeline_patches,
)


@pytest.mark.parametrize(
    ("usage_params", "expected_id"),
    [
        ({"consumable_type": 3}, 3),
        ({"consumable_id": 4}, 4),
        ({"consumableType": 5}, 5),
        (b"\x01\x06", 6),
    ],
)
def test_consumable_factory_reads_type_from_decoded_params(
    usage_params: object, expected_id: int
) -> None:
    packet = SimpleNamespace(
        timestamp=12.5,
        entity_id=123,
        method_args={
            "consumableUsageParams": usage_params,
            "workTimeLeft": 5.0,
        },
    )

    event = _consumable_factory(packet)

    assert event.consumable_id == expected_id
    assert event.consumable_type == expected_id
    assert event.work_time_left == 5.0
    assert event.timestamp == 12.5
    assert event.vehicle_id == 123


def test_apply_timeline_patches_replaces_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    factories = {"onConsumableUsed": lambda packet: packet}
    monkeypatch.setattr(stream, "_METHOD_FACTORIES", factories)

    apply_timeline_patches()

    assert factories["onConsumableUsed"] is _consumable_factory


def test_apply_timeline_patches_logs_noop_when_factory_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(stream, "_METHOD_FACTORIES", {})

    with caplog.at_level("DEBUG"):
        apply_timeline_patches()

    assert "onConsumableUsed factory is unavailable" in caplog.text


def test_apply_timeline_patches_logs_noop_when_event_shape_changed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    original = lambda packet: packet
    monkeypatch.setattr(stream, "_METHOD_FACTORIES", {"onConsumableUsed": original})
    monkeypatch.setattr(models, "ConsumableEvent", type("ChangedEvent", (), {}))

    with caplog.at_level("DEBUG"):
        apply_timeline_patches()

    assert stream._METHOD_FACTORIES["onConsumableUsed"] is original
    assert "ConsumableEvent fields have changed" in caplog.text

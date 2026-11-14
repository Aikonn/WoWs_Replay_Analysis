"""Small runtime fixes for wows-replay-parser, applied before its export runs.

export_timeline() runs the parser's CLI in a subprocess as
    sys.executable -c "from wows_replay_analysis.extract.parser_patches import
        apply_timeline_patches; apply_timeline_patches();
        from wows_replay_parser.cli import main; main()" export ...
so the patches live only in that subprocess. Each patch must be a no-op
(with a DEBUG log line) when the parser has changed so that the patched
name no longer exists, and must never make the export fail.

Patch 1 (2026-11-14): ConsumableEvent ids are always 0.
  Root cause: wows_replay_parser.events.stream._consumable() reads
  `consumableUsageParams["consumableType"]`, but the parser's own decoders
  return snake_case keys: `consumable_type` (packets/implemented_by_parsers
  ConsumableUsageParamsParser, with usage_type and optional x/z or target)
  or `consumable_id` (gamedata/blob_decoders, with slot_id). The
  consumable_id field is never set. The CLI also drops raw_data, so the
  value can't be recovered after export.
  Fix: replace the "onConsumableUsed" entry of stream._METHOD_FACTORIES with
  a factory that takes the type from `consumable_type`, `consumable_id` or
  `consumableType` (dict), or byte 1 (bytes, byte 0 is usage_type), and
  sets both consumable_type and consumable_id to it. The value is the
  game's consumable type id: name it with
  wows_replay_parser.consumable_calc.CONSUMABLE_TYPE_ID_MAP (0 crashCrew,
  ...) in Stage 2. Worth reporting upstream (toalba/wows-replay-parser).
"""

from __future__ import annotations

import inspect
import logging

logger = logging.getLogger(__name__)


def apply_timeline_patches() -> None:
    """Apply all patches above. Safe to call more than once."""
    try:
        from wows_replay_parser.events import stream
        from wows_replay_parser.events.models import ConsumableEvent
    except (ImportError, AttributeError) as exc:
        logger.debug("Skipping consumable parser patch: parser API unavailable: %s", exc)
        return

    factories = getattr(stream, "_METHOD_FACTORIES", None)
    if not isinstance(factories, dict):
        logger.debug("Skipping consumable parser patch: _METHOD_FACTORIES is unavailable")
        return
    if "onConsumableUsed" not in factories:
        logger.debug("Skipping consumable parser patch: onConsumableUsed factory is unavailable")
        return
    if not callable(factories["onConsumableUsed"]) or not isinstance(ConsumableEvent, type):
        logger.debug("Skipping consumable parser patch: parser event API has changed")
        return
    try:
        event_fields = inspect.signature(ConsumableEvent).parameters
    except (TypeError, ValueError):
        logger.debug("Skipping consumable parser patch: cannot inspect ConsumableEvent")
        return
    if not {
        "timestamp",
        "entity_id",
        "vehicle_id",
        "consumable_id",
        "consumable_type",
        "work_time_left",
        "raw_data",
    }.issubset(event_fields):
        logger.debug("Skipping consumable parser patch: ConsumableEvent fields have changed")
        return

    factories["onConsumableUsed"] = _consumable_factory


def _consumable_factory(packet: object) -> object:
    """Replacement for stream._consumable (Patch 1). Same ConsumableEvent
    fields as the original, plus the real consumable type id."""
    from wows_replay_parser.events.models import ConsumableEvent

    raw_args = getattr(packet, "method_args", None)
    args = raw_args if isinstance(raw_args, dict) else {}
    usage_params = args.get("consumableUsageParams", args.get("arg0"))

    consumable_type = 0
    if isinstance(usage_params, dict):
        for key in ("consumable_type", "consumable_id", "consumableType"):
            value = usage_params.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                consumable_type = value
                break
    elif isinstance(usage_params, (bytes, bytearray)) and len(usage_params) >= 2:
        consumable_type = usage_params[1]
    else:
        for key in ("consumable_type", "consumable_id", "consumableType"):
            value = args.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                consumable_type = value
                break

    work_time = args.get(
        "workTimeLeft", args.get("work_time_left", args.get("arg1", 0.0))
    )
    try:
        work_time_left = float(work_time or 0.0)
    except (TypeError, ValueError):
        work_time_left = 0.0

    entity_id = getattr(packet, "entity_id", 0)
    return ConsumableEvent(
        timestamp=getattr(packet, "timestamp", 0.0),
        entity_id=entity_id,
        vehicle_id=entity_id,
        consumable_id=consumable_type,
        consumable_type=consumable_type,
        work_time_left=work_time_left,
        raw_data=args,
    )

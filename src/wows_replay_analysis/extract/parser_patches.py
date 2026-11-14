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

import logging

logger = logging.getLogger(__name__)


def apply_timeline_patches() -> None:
    """Apply all patches above. Safe to call more than once."""
    raise NotImplementedError


def _consumable_factory(packet: object) -> object:
    """Replacement for stream._consumable (Patch 1). Same ConsumableEvent
    fields as the original, plus the real consumable type id."""
    raise NotImplementedError

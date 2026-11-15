"""Which raw extracts Stage 2 processes (README "Match filter").

Stage 1 extracts every replay. Stage 2 only builds summaries and database
rows for the battle types listed in config.match_groups (default: random
battles only, "pvp"), so brawls, events, co-op and ranked don't distort the
statistics. Changing the setting and running `process` rebuilds accordingly.

The battle type is the replay header's `matchGroup` (in meta.json), for
example "pvp" (random), "ranked", "clan", "pve" (co-op), "event", "brawl".
"""

from __future__ import annotations

import logging

from wows_replay_analysis.process.raw_loader import RawMatch

logger = logging.getLogger(__name__)

_WARNED_MISSING_MATCH_GROUPS: set[str] = set()


def match_group(raw: RawMatch) -> str | None:
    """Return the replay header's matchGroup (lower case), or None if missing."""
    value = raw.meta.get("matchGroup")
    if not isinstance(value, str) or not value.strip():
        header = raw.meta.get("header")
        value = header.get("matchGroup") if isinstance(header, dict) else value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def is_included(raw: RawMatch, match_groups: tuple[str, ...]) -> bool:
    """True if the match's group is in match_groups.

    A missing matchGroup is excluded and logged at WARNING once per match.
    """
    group = match_group(raw)
    if group is None:
        if raw.match_id not in _WARNED_MISSING_MATCH_GROUPS:
            logger.warning(
                "Excluding match %s because its matchGroup is missing or invalid",
                raw.match_id,
            )
            _WARNED_MISSING_MATCH_GROUPS.add(raw.match_id)
        return False
    return group in match_groups

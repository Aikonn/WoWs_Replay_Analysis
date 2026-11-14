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


def match_group(raw: RawMatch) -> str | None:
    """Return the replay header's matchGroup (lower case), or None if missing."""
    raise NotImplementedError


def is_included(raw: RawMatch, match_groups: tuple[str, ...]) -> bool:
    """True if the match's group is in match_groups.

    A missing matchGroup is excluded and logged at WARNING once per match.
    """
    raise NotImplementedError

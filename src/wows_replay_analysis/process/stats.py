"""Turns one raw extract into the database row for the multi-match statistics.

Built from the post-battle report (report.json); the timeline is only needed
for values the report does not have (e.g. time of death).
"""

from __future__ import annotations

from wows_replay_analysis.process.raw_loader import RawMatch


def match_stats_row(raw: RawMatch) -> dict:
    """Return one row for the `matches` table (columns in database.SCHEMA).

    Ship name, class and tier come from the post-battle report
    (battle_results_beta -> team_score), so GameParams is not needed.
    """
    raise NotImplementedError

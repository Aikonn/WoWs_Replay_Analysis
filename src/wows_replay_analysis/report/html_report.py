"""Generates the multi-match HTML trend report.

Purpose: readable on its own in a browser, and usable as context for an AI
discussion ("how did I play my Schlieffen this week?"). So: a self-contained
single HTML file (inline CSS, no external scripts), with the key numbers as
real text and tables, not only inside charts.

First version of the content:
    - Filter used (ship, date range) and number of matches.
    - Averages: damage, frags, spotting damage, damage received, base XP,
      win rate, survival rate, average time of death.
    - Per-match table in date order.
    - Trend: the same averages for the first and second half of the range,
      and the difference.

Use only the standard library (string templates / html.escape) unless a
template engine becomes clearly worth it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from wows_replay_analysis.config import Config


@dataclass(frozen=True)
class ReportFilter:
    """Which matches the report covers. None means "no limit"."""

    ship_name: str | None = None
    since: date | None = None
    until: date | None = None


def query_matches(config: Config, report_filter: ReportFilter) -> list[dict]:
    """Return matching rows from the matches table, oldest first.

    Ship name matching is case-insensitive and partial ("schlieffen" matches
    the full ship name).
    """
    raise NotImplementedError


def render_report(rows: list[dict], report_filter: ReportFilter) -> str:
    """Return the full HTML document for the given rows."""
    raise NotImplementedError


def generate_report(config: Config, report_filter: ReportFilter,
                    output: Path | None = None) -> Path:
    """Query, render and write the report.

    Default output: data/reports/<ship or all>_<since>_<until>.html.
    Return the written path.
    """
    raise NotImplementedError

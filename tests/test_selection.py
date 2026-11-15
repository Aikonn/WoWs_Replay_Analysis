from __future__ import annotations

import logging

from wows_replay_analysis.process.raw_loader import RawMatch
from wows_replay_analysis.process.selection import is_included, match_group


def raw_match(match_group_value: object = None) -> RawMatch:
    return RawMatch(
        "match",
        {"header": {"matchGroup": match_group_value}},
        report=None,
        timeline=None,
    )


def test_match_group_normalizes_case_and_whitespace() -> None:
    assert match_group(raw_match(" PvP ")) == "pvp"


def test_is_included_selects_configured_groups() -> None:
    assert is_included(raw_match("PvP"), ("pvp",))
    assert not is_included(raw_match("ranked"), ("pvp",))


def test_missing_match_group_is_excluded_and_warned(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert not is_included(raw_match(), ("pvp",))
        assert not is_included(raw_match(None), ("pvp",))

    assert len(caplog.records) == 1
    assert all("matchGroup is missing or invalid" in record.message for record in caplog.records)
    assert all("match" in record.message for record in caplog.records)

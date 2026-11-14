"""Smoke test: every module imports without errors."""

import importlib

import pytest

MODULES = [
    "wows_replay_analysis",
    "wows_replay_analysis.cli",
    "wows_replay_analysis.config",
    "wows_replay_analysis.extract.runner",
    "wows_replay_analysis.extract.report_parser",
    "wows_replay_analysis.extract.timeline_parser",
    "wows_replay_analysis.extract.parser_patches",
    "wows_replay_analysis.extract.gamedata",
    "wows_replay_analysis.process.raw_loader",
    "wows_replay_analysis.process.match_summary",
    "wows_replay_analysis.process.stats",
    "wows_replay_analysis.process.combat",
    "wows_replay_analysis.process.database",
    "wows_replay_analysis.process.selection",
    "wows_replay_analysis.process.minimap",
    "wows_replay_analysis.process.terrain",
    "wows_replay_analysis.updates",
    "wows_replay_analysis.gui",
    "wows_replay_analysis.report.html_report",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    importlib.import_module(name)

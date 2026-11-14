"""Shared pytest fixtures.

Real replays are not committed (test_data/ is in .gitignore). Tests that need
them use the `replay_files` fixture and are skipped when none are present.
Put a few .wowsreplay files into test_data/replays/ to run them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEST_REPLAYS_DIR = Path(__file__).resolve().parent.parent / "test_data" / "replays"


@pytest.fixture
def replay_files() -> list[Path]:
    """Return the replays in test_data/replays/, or skip the test if there are none."""
    files = sorted(TEST_REPLAYS_DIR.glob("*.wowsreplay"))
    if not files:
        pytest.skip("no replays in test_data/replays/")
    return files

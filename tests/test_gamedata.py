from __future__ import annotations

from pathlib import Path

import pytest

from wows_replay_analysis.extract import gamedata


@pytest.mark.parametrize(
    ("version", "expected"),
    [("15,10,0,13533378", "13533378"), ("15.10.0.13533378", "13533378")],
)
def test_build_id_from_version(version: str, expected: str) -> None:
    assert gamedata.build_id_from_version(version) == expected


def test_build_id_from_version_rejects_missing_build() -> None:
    with pytest.raises(ValueError, match="numeric build id"):
        gamedata.build_id_from_version("15,10,0")


def test_ensure_gamedata_syncs_and_returns_entity_defs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gamedata_dir = tmp_path / "gamedata"
    entity_defs = gamedata_dir / "data" / "scripts_entity" / "entity_defs"
    entity_defs.mkdir(parents=True)
    monkeypatch.setattr(gamedata, "sync_gamedata", lambda *args, **kwargs: True)
    monkeypatch.setattr(gamedata, "current_tag", lambda _: "v13533378")

    assert gamedata.ensure_gamedata(gamedata_dir, "15,10,0,13533378") == entity_defs


def test_ensure_gamedata_rejects_wrong_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gamedata_dir = tmp_path / "gamedata"
    monkeypatch.setattr(gamedata, "sync_gamedata", lambda *args, **kwargs: True)
    monkeypatch.setattr(gamedata, "current_tag", lambda _: "v13533377")

    with pytest.raises(RuntimeError, match="requires v13533378"):
        gamedata.ensure_gamedata(gamedata_dir, "15,10,0,13533378")


def test_current_tag_returns_exact_git_tag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 0
        stdout = "v13533378\n"

    monkeypatch.setattr(gamedata.subprocess, "run", lambda *args, **kwargs: Result())
    assert gamedata.current_tag(tmp_path) == "v13533378"

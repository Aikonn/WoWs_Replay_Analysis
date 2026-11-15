from __future__ import annotations

from pathlib import Path

import pytest

from wows_replay_analysis.config import load_config


def write_config(path: Path, replays_dir: str = "replays") -> None:
    path.write_text(
        f'[paths]\nreplays_dir = "{replays_dir}"\n'
        'data_dir = "data"\ngamedata_dir = "cache/gamedata"\n'
        "[extract]\nsnapshot_interval = 2.5\n",
        encoding="utf-8",
    )


def test_load_config_resolves_paths_from_config_directory(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    config_path = tmp_path / "config.toml"
    write_config(config_path)

    config = load_config(config_path)

    assert config.replays_dir == replay_dir.resolve()
    assert config.data_dir == (tmp_path / "data").resolve()
    assert config.gamedata_dir == (tmp_path / "cache" / "gamedata").resolve()
    assert config.snapshot_interval == 2.5
    assert config.match_groups == ("pvp",)
    assert not config.data_dir.exists()


def test_load_config_normalizes_process_match_groups(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    config_path = tmp_path / "config.toml"
    write_config(config_path)
    with config_path.open("a", encoding="utf-8") as config_file:
        config_file.write('\n[process]\nmatch_groups = [" PVP ", "Ranked"]\n')

    assert load_config(config_path).match_groups == ("pvp", "ranked")


@pytest.mark.parametrize("setting", ['match_groups = []', 'match_groups = "pvp"'])
def test_load_config_rejects_invalid_process_match_groups(
    tmp_path: Path, setting: str
) -> None:
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    config_path = tmp_path / "config.toml"
    write_config(config_path)
    with config_path.open("a", encoding="utf-8") as config_file:
        config_file.write(f"\n[process]\n{setting}\n")

    with pytest.raises(ValueError, match="Invalid process.match_groups"):
        load_config(config_path)


def test_load_config_requires_existing_replay_directory(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path)

    with pytest.raises(ValueError, match="Replay directory does not exist"):
        load_config(config_path)


def test_load_config_explains_missing_config_template(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="config.example.toml"):
        load_config(tmp_path / "missing.toml")

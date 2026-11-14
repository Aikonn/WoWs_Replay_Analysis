from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import struct

import pytest

from wows_replay_analysis.config import Config
from wows_replay_analysis.extract import runner


def make_replay(path: Path, header: dict[str, object] | None = None) -> None:
    encoded = json.dumps(header or {"clientVersionFromXml": "15,10,0,13533378"}).encode("utf-8")
    path.write_bytes(struct.pack("<III", 0x11343212, 3, len(encoded)) + encoded + b"replay")


def make_config(tmp_path: Path) -> Config:
    replays_dir = tmp_path / "replays"
    replays_dir.mkdir(exist_ok=True)
    return Config(replays_dir, tmp_path / "data", tmp_path / "cache" / "gamedata")


def test_find_replays_ignores_temp_and_sorts_oldest_first(tmp_path: Path) -> None:
    older = tmp_path / "older.wowsreplay"
    newer = tmp_path / "newer.wowsreplay"
    temporary = tmp_path / "temp.wowsreplay"
    for path in (older, newer, temporary):
        path.touch()
    os.utime(older, (10, 10))
    os.utime(newer, (20, 20))

    assert runner.find_replays(tmp_path) == [older, newer]


def test_match_id_uses_filename_without_extension(tmp_path: Path) -> None:
    assert runner.match_id_for(tmp_path / "match.wowsreplay") == "match"


def test_needs_extraction_handles_missing_old_and_current_metadata(tmp_path: Path) -> None:
    assert runner.needs_extraction(tmp_path / "missing")
    match_dir = tmp_path / "match"
    match_dir.mkdir()
    meta = match_dir / "meta.json"
    meta.write_text('{"extractor_version": 0}', encoding="utf-8")
    assert runner.needs_extraction(match_dir)
    meta.write_text(
        json.dumps({"extractor_version": runner.EXTRACTOR_VERSION}), encoding="utf-8"
    )
    assert not runner.needs_extraction(match_dir)
    meta.write_text("{", encoding="utf-8")
    assert runner.needs_extraction(match_dir)


def test_remove_tree_clears_readonly_file_and_folder(tmp_path: Path) -> None:
    tree = tmp_path / "readonly-tree"
    nested = tree / "nested"
    nested.mkdir(parents=True)
    readonly_file = nested / "readonly.txt"
    readonly_file.write_text("read only", encoding="utf-8")
    os.chmod(readonly_file, stat.S_IREAD)
    os.chmod(nested, stat.S_IREAD)

    runner.remove_tree(tree)

    assert not tree.exists()


def test_remove_tree_ignores_missing_path(tmp_path: Path) -> None:
    runner.remove_tree(tmp_path / "missing")


def test_cleanup_old_backups_removes_only_matching_backup_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_dir = tmp_path / "raw"
    temp_dir = tmp_path / "temp"
    raw_dir.mkdir()
    temp_dir.mkdir()
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(temp_dir))

    raw_backup = raw_dir / ".match.backup-a1b2"
    temp_backup = temp_dir / ".other.backup-012345"
    unrelated = raw_dir / ".match.backup-not-hex"
    regular = raw_dir / "match"
    for path in (raw_backup, temp_backup, unrelated, regular):
        path.mkdir()

    assert runner.cleanup_old_backups(raw_dir) == 2
    assert not raw_backup.exists()
    assert not temp_backup.exists()
    assert unrelated.is_dir()
    assert regular.is_dir()


def test_read_replay_header_reads_valid_json_and_rejects_bad_signature(tmp_path: Path) -> None:
    replay_path = tmp_path / "match.wowsreplay"
    header = {"mapName": "spaces/map", "clientVersionFromXml": "15,10,0,13533378"}
    make_replay(replay_path, header)

    assert runner.read_replay_header(replay_path) == header

    replay_path.write_bytes(b"invalid file")
    with pytest.raises(ValueError, match="Invalid replay signature"):
        runner.read_replay_header(replay_path)


def test_extract_replay_publishes_files_and_replaces_existing_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    replay_path = config.replays_dir / "match.wowsreplay"
    make_replay(replay_path, {"clientVersionFromXml": "15,10,0,13533378"})
    config.raw_dir.mkdir(parents=True)
    existing = config.raw_dir / "match"
    existing.mkdir()
    (existing / "obsolete.txt").write_text("old", encoding="utf-8")
    entity_defs = tmp_path / "entity_defs"

    monkeypatch.setattr(runner.gamedata, "ensure_gamedata", lambda *args: entity_defs)
    monkeypatch.setattr(runner.gamedata, "current_tag", lambda _: "v13533378")
    monkeypatch.setattr(runner.report_parser, "parse_report", lambda _: {"hidden": {}})

    def fake_timeline(
        replay: Path, entity: Path, output: Path, snapshot_interval: float
    ) -> None:
        assert replay == replay_path
        assert entity == entity_defs
        assert snapshot_interval == 5.0
        output.write_bytes(b"timeline")

    monkeypatch.setattr(runner.timeline_parser, "export_timeline", fake_timeline)

    runner.extract_replay(replay_path, config)

    match_dir = config.raw_dir / "match"
    assert not (match_dir / "obsolete.txt").exists()
    assert json.loads((match_dir / "report.json").read_text(encoding="utf-8")) == {
        "hidden": {}
    }
    assert (match_dir / "timeline.json.gz").read_bytes() == b"timeline"
    meta = json.loads((match_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["gamedata_tag"] == "v13533378"
    assert meta["source_sha256"] == hashlib.sha256(replay_path.read_bytes()).hexdigest()
    assert meta["header"]["clientVersionFromXml"] == "15,10,0,13533378"
    assert meta["errors"] == {}
    assert not list(config.raw_dir.glob(".match.*"))


def test_extract_replay_keeps_one_parser_output_when_the_other_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    replay_path = config.replays_dir / "match.wowsreplay"
    make_replay(replay_path)
    entity_defs = tmp_path / "entity_defs"
    monkeypatch.setattr(runner.gamedata, "ensure_gamedata", lambda *args: entity_defs)
    monkeypatch.setattr(runner.gamedata, "current_tag", lambda _: "v13533378")
    monkeypatch.setattr(
        runner.report_parser, "parse_report", lambda _: (_ for _ in ()).throw(ValueError("bad report"))
    )

    def fake_timeline(
        replay: Path, entity: Path, output: Path, snapshot_interval: float
    ) -> None:
        output.write_bytes(b"timeline")

    monkeypatch.setattr(runner.timeline_parser, "export_timeline", fake_timeline)

    runner.extract_replay(replay_path, config)

    match_dir = config.raw_dir / "match"
    assert (match_dir / "timeline.json.gz").exists()
    assert not (match_dir / "report.json").exists()
    meta = json.loads((match_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["errors"]["report"] == "bad report"


def test_extract_all_skips_current_and_continues_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    successful = config.replays_dir / "a.wowsreplay"
    broken = config.replays_dir / "b.wowsreplay"
    make_replay(successful)
    make_replay(broken)
    current_dir = config.raw_dir / "a"
    current_dir.mkdir(parents=True)
    (current_dir / "meta.json").write_text(
        json.dumps({"extractor_version": runner.EXTRACTOR_VERSION}), encoding="utf-8"
    )

    def fake_extract(path: Path, _: Config) -> None:
        if path == broken:
            raise RuntimeError("broken replay")

    monkeypatch.setattr(runner, "extract_replay", fake_extract)
    cleanup_calls: list[Path] = []
    monkeypatch.setattr(runner, "cleanup_old_backups", cleanup_calls.append)

    result = runner.extract_all(config)

    assert cleanup_calls == [config.raw_dir]
    assert result.skipped == ["a"]
    assert result.extracted == []
    assert result.failed == {"b": "broken replay"}


def test_extract_all_force_reextracts_current_extract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    replay = config.replays_dir / "a.wowsreplay"
    make_replay(replay)
    match_dir = config.raw_dir / "a"
    match_dir.mkdir(parents=True)
    (match_dir / "meta.json").write_text(
        json.dumps({"extractor_version": runner.EXTRACTOR_VERSION}), encoding="utf-8"
    )
    called: list[Path] = []

    def fake_extract(path: Path, _: Config) -> None:
        called.append(path)
        (match_dir / "meta.json").write_text('{"errors": {}}', encoding="utf-8")

    monkeypatch.setattr(runner, "extract_replay", fake_extract)

    result = runner.extract_all(config, force=True)

    assert called == [replay]
    assert result.extracted == ["a"]

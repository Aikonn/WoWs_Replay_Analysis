from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from wows_replay_analysis.extract import timeline_parser


def test_export_timeline_runs_full_export_and_compresses_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replay_path = tmp_path / "game.wowsreplay"
    entity_defs = tmp_path / "entity_defs"
    output_gz = tmp_path / "raw" / "timeline.json.gz"
    payload = {"meta": {"version": "15"}, "events": [{"type": "RawEvent"}]}

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(command: list[str], **kwargs: object) -> Result:
        assert command[0] == timeline_parser.sys.executable
        assert command[3:7] == [
            "export",
            str(replay_path),
            "--gamedata",
            str(entity_defs),
        ]
        assert "--no-positions" not in command
        assert "--no-properties" not in command
        assert "--no-raw" not in command
        Path(command[command.index("-o") + 1]).write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return Result()

    monkeypatch.setattr(timeline_parser.subprocess, "run", fake_run)

    timeline_parser.export_timeline(replay_path, entity_defs, output_gz, 2.5)

    with gzip.open(output_gz, "rt", encoding="utf-8") as file:
        assert json.load(file) == payload
    assert not list(output_gz.parent.glob("*.json"))


def test_export_timeline_raises_parser_stderr_and_keeps_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_gz = tmp_path / "timeline.json.gz"
    output_gz.write_bytes(b"existing")

    class Result:
        returncode = 1
        stderr = "parser failed"
        stdout = ""

    monkeypatch.setattr(timeline_parser.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="parser failed"):
        timeline_parser.export_timeline(tmp_path / "game.wowsreplay", tmp_path, output_gz)

    assert output_gz.read_bytes() == b"existing"
    assert list(tmp_path.iterdir()) == [output_gz]


def test_parser_version_reads_distribution_metadata() -> None:
    assert timeline_parser.parser_version()

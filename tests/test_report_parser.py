from __future__ import annotations

from pathlib import Path

import pytest

from wows_replay_analysis.extract import report_parser


def test_parse_report_returns_cli_shaped_json_compatible_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Replay:
        engine_data = {"clientVersionFromXml": "15, 10, 0, 13533378"}
        extra_data = [{"value": 1}]
        decrypted_data = b"replay"

    class Reader:
        def __init__(self, path: str) -> None:
            assert path == str(tmp_path / "game.wowsreplay")

        def get_replay_data(self) -> Replay:
            return Replay()

    class Player:
        def __init__(self, version: list[str]) -> None:
            assert version == ["15", "10", "0", "13533378"]

        def play(self, data: bytes, strict_mode: bool) -> None:
            assert data == b"replay"
            assert strict_mode is False

        def get_info(self) -> dict[str, object]:
            return {"opaque": b"raw"}

    monkeypatch.setattr(report_parser, "ReplayReader", Reader)
    monkeypatch.setattr(report_parser.wows, "ReplayPlayer", Player)

    result = report_parser.parse_report(tmp_path / "game.wowsreplay")

    assert result == {
        "open": Replay.engine_data,
        "extra_data": [{"value": 1}],
        "hidden": {"opaque": "b'raw'"},
        "error": None,
    }


def test_parse_report_propagates_unsupported_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Replay:
        engine_data = {"clientVersionFromXml": "unknown"}
        extra_data = []
        decrypted_data = b""

    class Reader:
        def __init__(self, path: str) -> None:
            pass

        def get_replay_data(self) -> Replay:
            return Replay()

    class Player:
        def __init__(self, version: list[str]) -> None:
            pass

        def play(self, data: bytes, strict_mode: bool) -> None:
            raise RuntimeError("unsupported game version")

    monkeypatch.setattr(report_parser, "ReplayReader", Reader)
    monkeypatch.setattr(report_parser.wows, "ReplayPlayer", Player)

    with pytest.raises(RuntimeError, match="unsupported game version"):
        report_parser.parse_report(tmp_path / "game.wowsreplay")


def test_parser_version_reads_distribution_metadata() -> None:
    assert report_parser.parser_version()

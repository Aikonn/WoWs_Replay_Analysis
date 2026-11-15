from __future__ import annotations

import importlib.util
import io
import logging
from pathlib import Path

import pytest

from wows_replay_analysis import cli
from wows_replay_analysis.config import Config
from wows_replay_analysis.extract.runner import ExtractResult


def test_build_parser_accepts_extract_force_and_config() -> None:
    args = cli.build_parser().parse_args(["--config", "my.toml", "extract", "--force"])

    assert args.command == "extract"
    assert args.force is True
    assert args.config == Path("my.toml")


def test_main_extracts_and_summarizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = Config(tmp_path, tmp_path / "data", tmp_path / "cache")
    monkeypatch.setattr(cli, "load_config", lambda _: config)

    def fake_extract(actual_config: Config, force: bool) -> ExtractResult:
        assert_config(actual_config, config, force)
        return ExtractResult(extracted=["one"], skipped=["two"])

    monkeypatch.setattr(cli, "extract_all", fake_extract)

    assert cli.main(["extract"]) == 0
    assert capsys.readouterr().out.strip() == "Extracted: 1, skipped: 1, failed: 0"


def assert_config(actual: Config, expected: Config, force: bool) -> None:
    assert actual is expected
    assert force is False


def test_main_returns_failure_for_failed_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_config", lambda _: Config(tmp_path, tmp_path, tmp_path))
    monkeypatch.setattr(
        cli, "extract_all", lambda *args, **kwargs: ExtractResult(failed={"one": "broken"})
    )

    assert cli.main(["extract"]) == 1


def test_main_process_dispatches_and_reports_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = Config(tmp_path, tmp_path / "data", tmp_path / "cache")
    monkeypatch.setattr(cli, "load_config", lambda _: config)
    calls: list[tuple[str, Config, bool]] = []
    monkeypatch.setattr(
        cli.database,
        "rebuild_database",
        lambda actual_config, force: calls.append(("database", actual_config, force)) or 3,
    )
    monkeypatch.setattr(
        cli.match_summary,
        "build_all_summaries",
        lambda actual_config, force: calls.append(("summaries", actual_config, force)) or 2,
    )

    assert cli.main(["process", "--force"]) == 0
    assert calls == [("database", config, True), ("summaries", config, True)]
    assert capsys.readouterr().out.splitlines() == [
        "Database rows written: 3",
        "Summaries written: 2",
    ]


def test_main_run_dispatches_extract_then_process_even_with_extract_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = Config(tmp_path, tmp_path / "data", tmp_path / "cache")
    monkeypatch.setattr(cli, "load_config", lambda _: config)
    calls: list[str] = []

    def fake_extract(actual_config: Config, force: bool) -> ExtractResult:
        assert actual_config is config
        assert force is True
        calls.append("extract")
        return ExtractResult(failed={"broken": "parser failed"})

    def fake_database(actual_config: Config, force: bool) -> int:
        assert actual_config is config
        assert force is True
        calls.append("database")
        return 0

    def fake_summaries(actual_config: Config, force: bool) -> int:
        assert actual_config is config
        assert force is True
        calls.append("summaries")
        return 0

    monkeypatch.setattr(cli, "extract_all", fake_extract)
    monkeypatch.setattr(cli.database, "rebuild_database", fake_database)
    monkeypatch.setattr(cli.match_summary, "build_all_summaries", fake_summaries)

    assert cli.main(["run", "--force"]) == 1
    assert calls == ["extract", "database", "summaries"]
    assert "Database rows written: 0" in capsys.readouterr().out


def test_main_reports_unimplemented_command_without_loading_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli, "load_config", lambda _: pytest.fail("unimplemented command must not load config")
    )

    assert cli.main(["report"]) == 2
    assert capsys.readouterr().out.strip() == "report is not implemented yet"


def test_quiet_parser_logs_filters_parser_noise_but_preserves_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.find_spec("replay_unpack")
    assert spec is not None and spec.origin is not None
    package_dir = Path(spec.origin).parent
    parser_file = package_dir / "core" / "network" / "player.py"
    root = logging.getLogger()
    parser_logger = logging.getLogger("replay_unpack")
    handler = logging.StreamHandler(io.StringIO())
    old_root_level = root.level
    old_parser_level = parser_logger.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    monkeypatch.setattr(parser_logger, "level", old_parser_level)

    try:
        cli.quiet_parser_logs(False)
        assert parser_logger.level == logging.ERROR

        handler.handle(logging.LogRecord(
            "root", logging.INFO, str(parser_file), 10, "unknown packet", (), None
        ))
        handler.handle(logging.LogRecord(
            "root", logging.ERROR, str(parser_file), 11, "parser failure", (), None
        ))
        handler.handle(logging.LogRecord(
            "app", logging.INFO, __file__, 12, "application info", (), None
        ))
        output = handler.stream.getvalue()
        assert "unknown packet" not in output
        assert "parser failure" in output
        assert "application info" in output

        cli.quiet_parser_logs(True)
        assert parser_logger.level == logging.DEBUG
        handler.handle(logging.LogRecord(
            "root", logging.INFO, str(parser_file), 13, "verbose parser info", (), None
        ))
        assert "verbose parser info" in handler.stream.getvalue()
    finally:
        cli.quiet_parser_logs(True)
        parser_logger.setLevel(old_parser_level)
        root.setLevel(old_root_level)
        root.removeHandler(handler)

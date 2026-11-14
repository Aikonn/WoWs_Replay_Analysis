from __future__ import annotations

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


def test_main_reports_unimplemented_command_without_loading_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli, "load_config", lambda _: pytest.fail("unimplemented command must not load config")
    )

    assert cli.main(["process"]) == 2
    assert capsys.readouterr().out.strip() == "process is not implemented yet"

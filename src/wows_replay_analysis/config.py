"""Loading and validating config.toml.

The format is documented in config.example.toml. Uses tomllib (Python 3.11+ stdlib).
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """Validated configuration. All paths are absolute."""

    replays_dir: Path
    data_dir: Path
    gamedata_dir: Path
    snapshot_interval: float = 5.0

    @property
    def raw_dir(self) -> Path:
        """Stage 1 output: data/raw/<match_id>/"""
        return self.data_dir / "raw"

    @property
    def matches_dir(self) -> Path:
        """Stage 2 output: data/matches/<match_id>.json"""
        return self.data_dir / "matches"

    @property
    def database_path(self) -> Path:
        """Stage 2 output: data/stats.sqlite"""
        return self.data_dir / "stats.sqlite"

    @property
    def reports_dir(self) -> Path:
        """Stage 3 output: data/reports/"""
        return self.data_dir / "reports"


def load_config(path: Path) -> Config:
    """Read config.toml and return a Config.

    - Relative paths are resolved against the folder containing config.toml.
    - Raise a clear error (mentioning config.example.toml) if the file is missing.
    - Raise a clear error if replays_dir does not exist.
    - data_dir and gamedata_dir may not exist yet; they are created when needed.
    """
    config_path = path.expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. "
            "Copy config.example.toml to config.toml and update its paths."
        )

    try:
        with config_path.open("rb") as config_file:
            values = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in {config_path}: {exc}") from exc

    paths = values.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"Missing [paths] section in {config_path}")

    def configured_path(name: str) -> Path:
        value = paths.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing or invalid paths.{name} in {config_path}")
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = config_path.parent / candidate
        return candidate.resolve()

    replays_dir = configured_path("replays_dir")
    if not replays_dir.is_dir():
        raise ValueError(f"Replay directory does not exist: {replays_dir}")

    extract = values.get("extract", {})
    if not isinstance(extract, dict):
        raise ValueError(f"Invalid [extract] section in {config_path}")
    snapshot_interval = extract.get("snapshot_interval", 5.0)
    if isinstance(snapshot_interval, bool) or not isinstance(snapshot_interval, (int, float)):
        raise ValueError(f"Invalid extract.snapshot_interval in {config_path}")
    if snapshot_interval <= 0:
        raise ValueError(f"extract.snapshot_interval must be positive in {config_path}")

    config = Config(
        replays_dir=replays_dir,
        data_dir=configured_path("data_dir"),
        gamedata_dir=configured_path("gamedata_dir"),
        snapshot_interval=float(snapshot_interval),
    )
    logger.debug("Loaded configuration from %s", config_path)
    return config

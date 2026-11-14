"""Loading and validating config.toml.

The format is documented in config.example.toml. Uses tomllib (Python 3.11+ stdlib).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    raise NotImplementedError

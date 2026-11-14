"""Island geometry for Stage 2: cover and line-of-sight facts for the match summary.

Reads the static map library (mapdata/<map>.json.gz, README "Map library").
AI models are poor at geometry from raw coordinates, so Stage 2 computes the
facts here and the summary states them in words and grid squares.

Game rule this models (confirmed by the owner, 2026-11-14): islands block
both spotting and shots, but only if they are tall enough where the line
between two ships crosses them. Very flat islands (e.g. on the map Trap)
block neither. So whether a line is blocked depends on the terrain height
along it, not just on crossing land.

The exact rule is not known. Start with: a line is blocked if the terrain
along it rises above BLOCK_HEIGHT_M anywhere. Then calibrate BLOCK_HEIGHT_M
on real replays (see is_blocked) and document the result here and in the
README.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Terrain height (metres) above which land blocks vision and shots. Placeholder:
# calibrate on real replays.
BLOCK_HEIGHT_M = 10.0


@dataclass(frozen=True)
class Island:
    id: int
    max_height_m: int
    blocks: bool                # max_height_m > BLOCK_HEIGHT_M
    grid_squares: tuple[str, ...]
    centre: tuple[float, float]  # world x, z


@dataclass(frozen=True)
class MapTerrain:
    """One map from the library: extent, height grid and islands."""

    name: str
    min_x: float
    max_x: float
    min_z: float
    max_z: float
    width: int                  # height grid size
    height: int
    heights: tuple[int, ...]    # row-major, metres
    islands: tuple[Island, ...]


def mapdata_dir() -> Path:
    """Return the repo's mapdata/ folder (next to pyproject.toml)."""
    raise NotImplementedError


def load_map(map_name: str) -> MapTerrain | None:
    """Load mapdata/<map>.json.gz; map_name may be "spaces/23_Shards".

    Return None (and log a warning once) if the map is not in the library,
    so a missing map never fails processing.
    """
    raise NotImplementedError


def height_at(terrain: MapTerrain, x: float, z: float) -> float:
    """Terrain height in metres at a world position (bilinear interpolation)."""
    raise NotImplementedError


def blocking_island(terrain: MapTerrain, a: tuple[float, float],
                    b: tuple[float, float]) -> Island | None:
    """Return the island that blocks the line a-b, or None if the line is clear.

    Sample the line every half grid cell; blocked where height_at >
    BLOCK_HEIGHT_M. Return the island containing the highest blocking sample.
    """
    raise NotImplementedError


def nearest_island(terrain: MapTerrain, x: float, z: float,
                   blocking_only: bool = True) -> tuple[Island, float, str] | None:
    """Return (island, distance to its shore in km, direction "N"/"NE"/...
    from me to the island), or None if there is none."""
    raise NotImplementedError


def is_blocked_check(raw, terrain: MapTerrain) -> dict:
    """Calibration helper (not used by the summary).

    For every 5-second state snapshot and every (allied ship, enemy ship) pair
    closer than the enemy's surface detection range, compare "was the enemy
    spotted" (timeline visibility) with blocking_island(). Find out where the
    detection range comes from (GameParams in the gamedata clone?) and report
    it; radar/hydro spotting ignores islands, so leave out periods where such
    a consumable was active if the timeline shows it. Return counts of agreement and disagreement per
    candidate BLOCK_HEIGHT_M (e.g. 0, 5, 10, 20, 40 m), plus a few example
    disagreements (time, ships, island), so the threshold can be chosen.
    """
    raise NotImplementedError

"""Minimap picture for one match: data/matches/<match_id>.png (Stage 2).

The AI can't know where the islands are from coordinates alone, so the
summary JSON gets a picture of the map with the ships' movements drawn on it,
plus a grid square ("E5") on every position in the JSON, so text and picture
can be read together.

Map source: the gamedata clone (cache/wows-gamedata, already on the replay's
build tag) has, per map, `data/spaces/<map>/`:
    minimap_water.png   background (water)
    minimap.png         islands, with transparency; draw it over the water
    space.settings      XML with <bounds minX maxX minY maxY> in chunks
<map> is the replay's map name, e.g. "23_Shards" (header "mapName" is
"spaces/23_Shards").

Coordinates: world x/z of ship positions map to the image via the map size
derived from space.settings. Work out the exact formula (chunk size, border
chunks) and verify it on real replays before trusting it: every ship track
must stay on water, spawns must sit near the map edges, and the result must
match landaire/wows-toolkit's minimap for the same replay. Document the
formula here and in the README.

Grid: the in-game minimap grid is 10 x 10. Rows are letters A-J from top to
bottom, columns are numbers 1-10 from left to right; "E5" = row E, column 5.

Picture content (first version, refine after real use):
- water + islands, grid lines and labels;
- my track as a thick line with a time label (m:ss) every 2 minutes and a
  marker at my death position;
- allied (green) and enemy (red) tracks as thin lines from the timeline state
  snapshots, only where the position is known, with a dot at the last known
  position and a cross where a ship died;
- capture points if the timeline provides them;
- legend: map name, my ship, colours.
Size about 800 x 800 px, PNG under about 300 KB.

Uses Pillow (the only new dependency, approved 2026-11-14).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from wows_replay_analysis.process.raw_loader import RawMatch

logger = logging.getLogger(__name__)

IMAGE_SIZE = 800  # pixels, square
GRID_ROWS = "ABCDEFGHIJ"


@dataclass(frozen=True)
class MapInfo:
    """What is needed to place world positions on the minimap image."""

    name: str              # e.g. "23_Shards"
    water_png: Path
    islands_png: Path
    space_size: float      # world units across the whole minimap (square)
    # Add origin fields if the map is not centred on world 0,0.


def load_map_info(gamedata_dir: Path, map_name: str) -> MapInfo:
    """Read data/spaces/<map_name>/space.settings and locate both PNGs.

    map_name may be "spaces/23_Shards" or "23_Shards". Raise FileNotFoundError
    with the map name if the folder is missing.
    """
    raise NotImplementedError


def world_to_unit(map_info: MapInfo, x: float, z: float) -> tuple[float, float]:
    """Convert world x/z to minimap coordinates in 0..1 (0,0 = top-left).

    Check the axis directions (z usually points north = up on the image).
    """
    raise NotImplementedError


def grid_square(map_info: MapInfo, x: float, z: float) -> str:
    """Return the minimap grid square for a world position, e.g. "E5"."""
    raise NotImplementedError


def render_minimap(raw: RawMatch, map_info: MapInfo, output_path: Path) -> Path:
    """Draw the picture described in the module docstring and write it atomically.

    Return output_path.
    """
    raise NotImplementedError

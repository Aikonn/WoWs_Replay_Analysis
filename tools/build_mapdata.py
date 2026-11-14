"""Generate the map library (mapdata/<map>.json.gz) from the installed game.

Run by the owner only, when random battles get a new or reworked map:
    python tools/build_mapdata.py --game "C:/Games/World_of_Warships" [--maps 23_Shards ...]
The output is committed to the repo; normal users never run this.

Source: each map's terrain heightmap `terrain.bin` inside the game's packed
resources (res_packages/*.pkg + idx). Investigate and document here:
- How to get terrain.bin out of the packages. Options: the official
  Wargaming `wowsunpack.exe`, or landaire's `wowsunpack` crate/CLI
  (https://docs.rs/wowsunpack, part of wows-toolkit). Prefer a tool the owner
  runs once into a temp folder over reimplementing the package format.
- Format (per wowsunpack's src/models/terrain.rs): 16-byte header, all
  little-endian u32: magic `trb\\0` (0x00627274), width, height, tile info
  (low u16 = tile_size, high u16 = tiles_per_axis). Body: RLE stream of u32
  words holding f32 values; a repeat is stored as [val, val, count]
  (count < 0x100000 = total occurrences). After decoding, a preamble of
  min/max pairs precedes the heightmap; the heightmap is the LAST
  width*height values, row-major, in metres. Check the licence of the crate
  and credit it in this docstring.

Per map, write (see README "Map library" for the exact format):
- the world extent the heightmap covers (verify by overlaying the land mask
  on the gamedata minimap.png: the outlines must match);
- the height grid, downsampled to at most 256 x 256, metres rounded to ints;
- the islands: connected land areas (height > SEA_LEVEL_M), each with a
  simplified outline (Douglas-Peucker, a few dozen points), max height,
  area and the grid squares it covers.

Only the standard library plus Pillow (already a dependency).
"""

from __future__ import annotations

import argparse
from pathlib import Path

SEA_LEVEL_M = 0.0          # verify on real data
MAX_GRID = 256
OUTLINE_TOLERANCE = 0.002  # Douglas-Peucker tolerance as a fraction of map size


def parse_terrain(data: bytes) -> tuple[int, int, list[float]]:
    """Decode terrain.bin bytes into (width, height, row-major heights in metres)."""
    raise NotImplementedError


def build_map(map_name: str, terrain_bin: Path, gamedata_dir: Path) -> dict:
    """Build the map-library dict for one map (format in README "Map library")."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """CLI: extract terrain for the requested maps and write mapdata/<map>.json.gz."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", type=Path, required=True, help="Game installation folder")
    parser.add_argument("--maps", nargs="*", help="Map names (default: all random-battle maps)")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "mapdata")
    args = parser.parse_args(argv)
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())

"""Stage 1: raw extraction. Turns .wowsreplay files into raw extracts in data/raw/."""

# Bump this whenever the raw extract format or the parser setup changes.
# Replays whose meta.json has a lower version are re-extracted.
EXTRACTOR_VERSION = 1

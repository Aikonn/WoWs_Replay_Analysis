"""Stage 2: processing. Builds match summaries and the SQLite database from raw extracts.

Works only from data/raw/, never from the original replays, so it can be
rebuilt at any time.
"""

# Bump this whenever the summary format or the database schema changes.
# Matches processed with a lower version are rebuilt.
PROCESSOR_VERSION = 3  # 4: minimap/grid + islands (3b/3c)

"""Simple desktop window for the tool (README "GUI").

Tkinter only (ships with Python on Windows, no extra install). Started with
`python -m wows_replay_analysis gui` or the `start_gui.bat` launcher.

Layout (one window, about 900 x 600):

    [ Process new replays ] [ Check for updates ] [ Update ] [ Open data folder ]
    Status line: "Last run: 3 extracted, 0 failed" / update states
    Recent matches (ttk.Treeview, newest first, last 50 from stats.sqlite):
        Date | Ship | Map | Result | Damage | [Open] [Show in Explorer]
    Log pane (read-only Text, last ~500 lines of the tool's logging output)

Behaviour:
- Buttons run the existing functions (extract_all + Stage 2, updates.check_all,
  updates.update_all) in a background thread. The UI thread never blocks;
  workers report back through a queue.Queue polled with `root.after(100, ...)`.
  Tkinter widgets are only touched from the UI thread.
- While a job runs, all action buttons are disabled.
- "Open" opens data/matches/<match_id>.json with the default app
  (os.startfile); "Show in Explorer" runs `explorer /select,<path>` on the
  summary JSON (the PNG sits next to it).
- Double-click on a row = Open.
- On start: load the config (on error show a message box explaining how to
  create config.toml from config.example.toml), fill the list, and run
  updates.check_all in the background so the status line shows if updates
  are available. Never update without the user pressing Update.
- After a tool update, tell the user to restart the window.
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from pathlib import Path

from wows_replay_analysis.config import Config

logger = logging.getLogger(__name__)

RECENT_LIMIT = 50


class QueueLogHandler(logging.Handler):
    """Logging handler that puts formatted records on a queue for the log pane."""

    def __init__(self, messages: queue.Queue) -> None:
        raise NotImplementedError

    def emit(self, record: logging.LogRecord) -> None:
        raise NotImplementedError


def recent_matches(database_path: Path, limit: int = RECENT_LIMIT) -> list[dict]:
    """Return the newest matches from stats.sqlite (match_id, played_at,
    ship_name, map_name, result, damage), newest first. Empty list if the
    database doesn't exist yet."""
    raise NotImplementedError


def show_in_explorer(path: Path) -> None:
    """Open Windows Explorer with `path` selected (`explorer /select,<path>`)."""
    raise NotImplementedError


class App:
    """The main window. Construct with a Tk root and the config path."""

    def __init__(self, root: tk.Tk, config_path: Path) -> None:
        raise NotImplementedError

    def run_in_background(self, label: str, job) -> None:  # job: Callable[[], object]
        """Disable the buttons, run job in a thread, report result via the queue."""
        raise NotImplementedError

    def process_new_replays(self) -> None:
        """Button: extract + process (same as the `run` command)."""
        raise NotImplementedError

    def check_updates(self) -> None:
        """Button: updates.check_all, show the states in the status line."""
        raise NotImplementedError

    def update(self) -> None:
        """Button: confirm with a dialog, then updates.update_all."""
        raise NotImplementedError

    def refresh_matches(self) -> None:
        """Reload the recent matches list from the database."""
        raise NotImplementedError


def main(config_path: Path) -> int:
    """Create the window and run the Tk main loop. Return the exit code."""
    raise NotImplementedError


def run() -> int:
    """Entry point for the `wows-analysis-gui` launcher and start_gui.bat.

    Uses <app folder>/config.toml (updates.app_dir()), not the current folder,
    because a double-clicked launcher can start anywhere.
    """
    raise NotImplementedError


def _load_config_or_none(config_path: Path) -> Config | None:
    """Load the config; on error show a message box and return None."""
    raise NotImplementedError

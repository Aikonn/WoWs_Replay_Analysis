"""Update checks and updates for the tool, the replay parsers and the gamedata.

Not part of the three stages; used by the `check` and `update` commands and
by the GUI (see README "Updates").

Three components can go out of date after a game patch or a code change:

1. **The tool itself** (this repo). Updated without git: ask the GitHub API
   for the latest commit on the configured branch, compare it with the commit
   stored in `.installed_commit` in the app folder, and if they differ,
   download the branch as a zip and replace the code files. User files stay
   untouched (see PRESERVED). The owner works in a git clone: if the app
   folder contains `.git`, never overwrite anything; report "use git pull".
2. **The replay parsers** (replays_unpack and wows-replay-parser), installed
   from GitHub with pip. Their installed commit is in the package's
   `direct_url.json` (PEP 610, `vcs_info.commit_id`); compare it with the
   latest upstream commit. Update with
   `sys.executable -m pip install --upgrade --force-reinstall --no-deps <url>`.
3. **The gamedata** (wows-render-gamedata). Already synced automatically per
   replay by `extract.gamedata.ensure_gamedata()`. Here we only check that the
   upstream repo has a tag `v<build_id>` for the newest replay's game build
   (`git ls-remote --tags`), so the user knows when upstream hasn't caught up
   with a new patch yet.

Use only the standard library (`urllib.request`, `json`, `zipfile`,
`subprocess`). All network calls have a timeout and fail with a clear message;
a failed check must never break extraction or processing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from wows_replay_analysis.config import Config

logger = logging.getLogger(__name__)

# Upstream repos of the parsers: (distribution name, GitHub "owner/repo", pip URL).
PARSER_PACKAGES: tuple[tuple[str, str, str], ...] = (
    (
        "World-of-Warships-replays-parser",
        "Monstrofil/replays_unpack",
        "git+https://github.com/Monstrofil/replays_unpack.git",
    ),
    (
        "wows-replay-parser",
        "toalba/wows-replay-parser",
        "git+https://github.com/toalba/wows-replay-parser.git",
    ),
)

GAMEDATA_REPO_URL = "https://github.com/toalba/wows-render-gamedata.git"

# File in the app folder holding the commit sha of the installed tool version.
INSTALLED_COMMIT_FILE = ".installed_commit"

# Top-level names in the app folder that a tool update never touches.
PRESERVED: frozenset[str] = frozenset({
    "config.toml", "data", "cache", ".venv", "venv", "test_data", "_tools",
    INSTALLED_COMMIT_FILE, ".git",
})


@dataclass
class ComponentStatus:
    """Result of one check, shown in the CLI and the GUI.

    state: "up_to_date", "update_available", "unsupported" (upstream has no
    support for the newest replay's game version yet), or "unknown" (the check
    itself failed, e.g. no internet).
    """

    name: str            # "tool", "replays_unpack", "wows-replay-parser", "gamedata"
    state: str
    installed: str | None = None   # short commit sha or tag
    latest: str | None = None
    message: str = ""    # one human-readable line


def app_dir() -> Path:
    """Return the app folder: the folder containing pyproject.toml above this package.

    The tool is installed with `pip install -e .`, so this is the repo/zip root.
    """
    raise NotImplementedError


def latest_commit(repo: str, branch: str, token: str | None = None) -> str:
    """Return the full sha of the newest commit on `branch` of GitHub `repo`.

    GET https://api.github.com/repos/{repo}/commits/{branch} with header
    `Accept: application/vnd.github.sha` (the body is the sha). Send
    `Authorization: Bearer <token>` only when a token is configured (the repo
    is public, so normally none). Timeout 15 s.
    """
    raise NotImplementedError


def check_tool(config: Config) -> ComponentStatus:
    """Compare `.installed_commit` with the latest commit of config.update_repo/branch.

    - App folder has `.git`: state "up_to_date" is not knowable this way;
      return state "unknown" with message "git clone: update with git pull".
    - No `.installed_commit`: state "update_available" (first update writes it).
    """
    raise NotImplementedError


def update_tool(config: Config) -> ComponentStatus:
    """Download the branch zip and replace the code files in the app folder.

    Steps:
    1. Refuse if the app folder has `.git` (return the check_tool status).
    2. Download https://api.github.com/repos/{repo}/zipball/{branch} into a
       temp folder and extract it (the zip has one top folder, skip it).
    3. For every top-level entry of the new version that is not in PRESERVED:
       replace it (folders via extract.runner.remove_tree, then copy).
       Delete top-level entries that no longer exist upstream, except PRESERVED.
       Never touch PRESERVED names even if the zip contains them.
    4. If pyproject.toml changed, run `sys.executable -m pip install -e <app_dir>`
       so new dependencies get installed.
    5. Write the new sha to `.installed_commit` last (atomic write).
    A running GUI must restart afterwards; the message says so.
    """
    raise NotImplementedError


def installed_parser_commit(distribution: str) -> str | None:
    """Return the installed commit of a parser from its direct_url.json, or None.

    Use importlib.metadata.distribution(name).read_text("direct_url.json").
    """
    raise NotImplementedError


def check_parsers(config: Config) -> list[ComponentStatus]:
    """One status per entry of PARSER_PACKAGES.

    "update_available" when the installed commit differs from the latest
    upstream commit on the default branch. Additionally, for replays_unpack,
    return "unsupported" when the newest replay's game version has no version
    folder in the installed package (check how replays_unpack lays out its
    per-version folders and document it here).
    """
    raise NotImplementedError


def update_parsers() -> list[ComponentStatus]:
    """Reinstall both parsers from GitHub (pip --upgrade --force-reinstall --no-deps).

    Run pip as a subprocess with sys.executable, capture its output, log it at
    DEBUG and put the last error line into the status message on failure.
    """
    raise NotImplementedError


def newest_replay_version(config: Config) -> str | None:
    """Return the game version (e.g. "15,10,0,13533378") of the newest replay.

    Use extract.runner.find_replays + read_replay_header ("clientVersionFromExe").
    None if there are no replays.
    """
    raise NotImplementedError


def check_gamedata(config: Config) -> ComponentStatus:
    """Check that upstream gamedata has the tag v<build_id> for the newest replay.

    `git ls-remote --tags GAMEDATA_REPO_URL v<build_id>`. "unsupported" if the
    tag is missing (new patch, upstream not updated yet: those replays can't be
    extracted until it is). The local checkout itself is handled by
    ensure_gamedata() during extraction.
    """
    raise NotImplementedError


def check_all(config: Config) -> list[ComponentStatus]:
    """Run every check; a failing check becomes state "unknown", never an exception."""
    raise NotImplementedError


def update_all(config: Config) -> list[ComponentStatus]:
    """Update the parsers, then the tool. Return the new statuses."""
    raise NotImplementedError

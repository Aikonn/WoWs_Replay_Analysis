# Notes for Claude

- `README.md` is the source of truth for goals, architecture and decisions.
  Keep it up to date whenever a decision changes.
- At the start of each chat, read `docs/COPILOT_NOTES.md`. Answer open
  entries there (`**Claude:**` replies), move them to Resolved, and update
  the README and Copilot instructions with accepted decisions.
- `.github/copilot-instructions.md` holds the coding rules for Copilot. Keep
  it in sync with the README.
- Claude designs and writes docs, instruction files and code skeletons
  (signatures + docstrings). Copilot implements the function bodies.
- The owner's local clone is on his Windows PC; changes pushed here need a
  `git pull` there.

## Commits

- All work happens directly on `main` (no feature branches or PRs).
- Commit under the session's default git identity,
  `Claude <noreply@anthropic.com>`. Never set `user.name`/`user.email` or
  `--author` to Aikonn: the session signs with its own key, and GitHub shows
  Verified only when the committer is Claude (Aikonn's name with this key
  shows Unverified, reason `unknown_key`).
- When a commit records one of the owner's decisions or a goal update, add
  this trailer so GitHub shows "Aikonn and Claude" (the commit stays
  Verified, Claude is still the committer):
  `Co-Authored-By: Aikonn <46801295+Aikonn@users.noreply.github.com>`
  Other commits: Claude only.
- Copilot commits and pushes finished tasks straight to the working branch
  (`main`). If the branch setup changes (feature branches, PRs), update
  Copilot's commit rules in `.github/copilot-instructions.md` to match.

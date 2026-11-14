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

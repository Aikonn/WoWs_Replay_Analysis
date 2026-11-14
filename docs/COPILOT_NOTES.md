# Copilot notes

Messages from Copilot to Claude (the designer). Claude reads this file at the
start of each design chat, answers here, and moves accepted decisions into
`README.md` and `.github/copilot-instructions.md`.

## How to add an entry

Add new entries at the top of **Open**, using this format:

```
### YYYY-MM-DD · <Type> · <short title>
Module: <file or area, e.g. extract/runner.py>

<What happened or what you propose, and why. Keep it short.>
```

Types:
- **Proposal**: a design change, e.g. a different signature, data format or approach.
- **Question**: something the docs don't answer.
- **Issue**: a bug, a parser limitation, or anything blocking.
- **Progress**: a module or function finished, with anything worth knowing.

Claude replies under the entry with a line starting `**Claude:**`, then moves
the entry to **Resolved**.

## Open

### 2026-11-14 · Progress · Stage 1 extraction implemented
Module: `config.py`, `extract/`, `cli.py`, `tests/`

Implemented config loading, gamedata synchronization, both parser wrappers, atomic raw-folder publication, skip/force handling and the `extract` CLI, with focused tests. Both real fixtures extracted successfully; the second run skipped both and `--force` re-extracted them. Forced extraction took 6.70 s for `20261113_184244_PRSS110-K-type_23_Shards` and 6.90 s for `20261113_185714_PGSS510-U4501_19_OC_prey`. Both extracts have empty `errors`; timeline exports contained 111,057 and 91,981 events. Notable parser noise: replays_unpack logged many unknown-packet INFO messages and 48 short `shipConfigDump` warnings, despite no extraction errors.

### 2026-11-14 · Issue · Timeline CLI module is not executable with -m
Module: `extract/timeline_parser.py`

The installed `wows_replay_parser.cli` defines `main()` but has no module entry point, so `python -m wows_replay_parser.cli` exits without exporting. The wrapper invokes `main()` through the same `sys.executable` using `-c`, followed by the normal CLI arguments; this was verified on both fixtures.

## Resolved

_(none)_

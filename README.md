# Claude Code Infinite Perfect Context (CCipc)

> Reverse compaction for Claude Code: search past conversation turns and auto-fork into them with full pre-compaction fidelity.

[![PyPI](https://img.shields.io/pypi/v/claude-code-infinite-perfect-context?color=green)](https://pypi.org/project/claude-code-infinite-perfect-context/)
[![Release Date](https://img.shields.io/github/release-date/DazzleML/Claude-Code-Infinite-Perfect-Context?color=green)](https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/license-GPL--3.0--or--later-green.svg)](LICENSE)
[![Installs](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/djdarcy/d0f7a19fcf65519b1a422e03a5c23fb8/raw/installs.json)](https://dazzleml.github.io/Claude-Code-Infinite-Perfect-Context/stats/#installs)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](docs/platform-support.md)

> [!WARNING]
> **Pre-Alpha software -- scaffolding only.** This release wires up the package layout, CLI dispatcher, aggregator pattern, and version/release tooling. No functional reverse-compaction commands are implemented yet beyond `--version`, `--help`, `list`, and `info`. Phase 1 (the search-then-fork POC, Mode A, single session) is the first release that will actually do anything useful -- see [Issue #4](https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/issues/4). Until then, treat this repo as a design artifact and architectural placeholder. Expect breaking changes, missing tools, and interface churn until the alpha series begins.

See the [Roadmap](https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/issues/1) for phased plans and current status.

## What is this?

Claude Code's compaction summarizes the past and projects forward in time. While this is useful, it also lossy and Claude's understanding slowly degrades. `ccipc` inverts that direction: store the present and travel back to a chosen past moment, optionally bringing forward a summary of where you ended up. Two modes:

- **Mode A -- Verbatim past**: hydrate a session into the exact pre-compaction state at turn N.
- **Mode B -- Past + summarized present**: same as Mode A, with a synthesized summary of the present appended after the historical prefix.

The user-facing operation: **search by intent or commit hash, auto-fork into that exact past moment, continue work**.

## Architecture

`ccipc` is a composable Unix-style toolkit built on [`dazzlecmd-lib`](https://github.com/DazzleTools/dazzlecmd)'s aggregator pattern. Pipeline composition is at the shell level via JSONL stdin/stdout:

```bash
ccipc search-multi --term "auth refactor"           # find candidate past turns
  | ccipc find-boundary --before                    # walk back to a turn boundary
  | ccipc cassette [--with-summary <text>]          # build a synthetic JSONL
  | ccipc hydrate                                   # install + claude --resume
```

Each subcommand is a focused tool. Shared logic lives in `ccipc-lib` (Python package). New tools are added by dropping a directory under `tools/<kit>/<name>/` with a `.ccipc.json` manifest plus a Python script -- the aggregator engine discovers them automatically.

## Installation

Pre-Alpha -- not yet on PyPI. Install editably from source:

```bash
git clone https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context.git
cd Claude-Code-Infinite-Perfect-Context
pip install -e .
ccipc --version
ccipc list           # see available tools
ccipc info <tool>    # tool details
```

Requires `dazzlecmd-lib` (currently installable only from local source; PyPI publishing TBD).

## Related projects

- [`claude-session-backup`](https://github.com/DazzleML/Claude-Session-Backup) (`csb`) -- git-backed session storage. `ccipc` reads from `csb`'s SQLite index and (for compacted sessions) its git history.
- [`claude-session-logger`](https://github.com/DazzleML/dazzle-claude-plugins) -- transcript mirroring with structured tool-call logs.
- [`dazzletreelib`](https://github.com/djdarcy/dazzle-tree-lib) -- tree traversal library used for fork-graph navigation (Phase 4).
- [`dazzlecmd`](https://github.com/DazzleTools/dazzlecmd) -- the `dz` CLI family `ccipc`'s aggregator builds on.

## Documentation

- [Roadmap](https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/issues/1) 
- [Quick Notes -- Bugs, Features, Ideas](https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/issues/2) 
- Also see "docs" for additional details.

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

Like the project?

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)

## License

Copyright (C) 2026 Dustin Darcy

This project is licensed under the GNU General Public License v3.0 -- see the [LICENSE](LICENSE) file for details.

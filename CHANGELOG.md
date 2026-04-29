# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-28

### Added
- Initial project scaffolding via `DazzleTools/git-repokit-template`.
- Subtree at `scripts/` from `git-repokit-common` (version-sync, hooks, common scripts).
- Pre-commit / post-commit / pre-push hooks installed.
- Source layout switched to `src/`:
  - `src/ccipc_lib/` -- shared Python core (jsonl parser, csb client, cost estimator, cassette builder; placeholders pending Phase 1).
  - `src/ccipc/` -- CLI dispatcher built on `dazzlecmd-lib`'s `AggregatorEngine` (mirrors the wtf-windows pattern).
- Aggregator pattern wiring:
  - `tools/core/search-multi/` placeholder with `.ccipc.json` manifest + Python entry script.
  - `kits/core.kit.json` declares the core kit.
  - `_find_ccipc_project_root()` helper to handle installed-package vs source-tree resolution.
  - `_build_ccipc_help` epilog builder so `ccipc --help` surfaces both lib-default meta-commands and discovered tools (mirrors `dz` shape).
- CLI invocation: `ccipc` and `claude-code-infinite-perfect-context` (alias) entry points.
- Version module at `src/ccipc_lib/_version.py` with PEP 440 compliance helpers; `src/ccipc/_version.py` re-exports for convenience.
- `private/` workspace via `dz private-init` for design docs and project-internal notes.
- Initial design plan and user philosophy notes captured in `private/claude/`.
- GitHub repo configured: discussions enabled, topics set, custom labels created (pinned, evergreen, roadmap, scratchpad, architecture, epic, ideas, CurrentTask, NextTask, phase, companion-tool).
- GitHub issues created: #1 Roadmap (evergreen), #2 Quick Notes (evergreen), #3-#8 Phases 0-5, #9 Companion `dz git-packit`, #10 License decision.
- ghtraf traffic tracker integrated: badge gist, archive gist, dashboard at `docs/stats/`, Installs badge in README, history baseline seeded.
- Documentation: `README.md`, `ROADMAP.md`, `docs/platform-support.md`.

### Notes
- `dazzlecmd-lib` is currently installed editably from local source; not yet published to PyPI. The pyproject dependency declaration uses a simple version constraint and assumes the package is resolvable in the user's pip environment. This may switch to a git URL or vendored copy once distribution policy is decided.
- POC implementation (Phase 1: search-then-fork, Mode A) has not started yet; this release is pure scaffolding.
- ghtraf workflow secret (`TRAFFIC_GIST_TOKEN`) must be set manually by the maintainer before scheduled stats runs will succeed.

[Unreleased]: https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/releases/tag/v0.1.0

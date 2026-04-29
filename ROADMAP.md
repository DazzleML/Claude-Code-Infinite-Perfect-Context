# Roadmap

> See **[Issue #1](https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/issues/1)** for the live, evergreen roadmap. This file is a static summary.

## Phases

| Phase | Description | Status |
|---|---|---|
| 0 | Project scaffolding (template, subtree, hooks, src layout, aggregator pattern) | In progress |
| 1 | POC: search-then-fork (Mode A, single session, commit-oriented search) | Planned |
| 2 | Multi-session search + git-history recovery from `csb` | Planned |
| 3 | Mode B: past + summarized present (synthesized bridging message) | Planned |
| 4 | Fork graph navigation via `DazzleTreeLib` adapter | Planned |
| 5 | Skill bridge (`/ipc-search`, `/ipc-fork-from`, `/ipc-fork-from-with-summary`) | Planned |
| 6 | Optional enhancements (`PostCompact` hook, cross-project search, semantic retriever) | Deferred |

## Current focus

**Phase 0** -- project scaffolding via `git-repokit-template` + `dazzlecmd-lib` aggregator pattern. The composable Unix-style toolkit shape is set; placeholder tool stubs will be replaced with real implementations starting in Phase 1.

## Companion work

- `dz git-packit` (separate dev-workflow) -- a BBPack-style world-state snapshot tool. `ccipc`-hydrated sessions reference world-tree state via this tool's bundles.

## See also

- [Issue #1 -- Roadmap](https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/issues/1) (live)
- [Issue #2 -- Quick Notes / Brainstorming](https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/issues/2) (live)

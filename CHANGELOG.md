# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — Phase 1: search-then-fork POC (Mode A, single-session)

Library (`src/ccipc_lib/`):
- `slug.py` -- Claude Code slug derivation (`sanitize_path`, `canonicalize_path`, `slug_from_cwd`); djb2 path hash for paths >200 chars.
- `jsonl_search.py` -- port of csb's `extract_strings` / `search_transcript` for JSONL transcript searches.
- `boundaries.py` -- turn-boundary classifier; walks JSONL backward for nearest user-turn; respects `SystemCompactBoundaryMessage` as hard stop unless `--include-pre-compact`.
- `cost.py` -- token estimation, model resolution (`--model > ANTHROPIC_MODEL > default`), plan-aware budget warnings, compaction circuit-breaker warnings.
- `cc_compat.py` -- Claude Code version parsing + SemVer-compatible cassette-vs-installed-CC checking; major-mismatch raises, minor-mismatch with `force=True` warns.
- `config.py` -- `~/.claude/ccipc/config.toml` load/save with v1 schema, interactive TTY prompts, non-TTY error path, migration framework.
- `errors.py` -- exit-code matrix (1, 2, 3, 4, 5, 6, 7, 8, 9, 99) + `CCIPCError` subclasses; each error carries WHY and WHAT-TO-DO recovery hints.
- `schema.py` -- `SearchHit` / `BoundaryHit` etc., JSONL stdin/stdout helpers, multi-record fan-in rejection (exit 7).
- `cc_constants.py` -- verified Claude Code constants (`MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3`, plan-tied autocompact budgets, sidecar required-extensions list, helpers `get_autocompact_threshold`, `get_blocking_limit`, `get_effective_context_window`).
- `tool_meta.py` -- load a tool's own `.ccipc.json` from the tool's own location and surface the manifest's description through `argparse` so `ccipc info <tool>` and `ccipc <tool> --help` show the same text.

Tools (`tools/core/`):
- `search/` -- JSONL grep over a session, AND-search across multiple terms, type filter, corruption tolerance.
- `find-boundary/` -- walks back to user-turn boundary with plan-aware `--headroom-tokens` default and `--include-pre-compact` opt-in.
- `cassette/` -- Mode A verbatim prefix builder; atomic write (tmp + os.replace) with the temp file written next to the target; emits 3 sidecars (`<uuid>.json`, `<uuid>.name-cache`, `<uuid>.source`); inline `ccipc_meta` on first user-message line.
- `cost-estimate/` -- plan-aware cost preview (always exit 0, warnings to stderr); plan resolution precedence `--plan > config > interactive prompt > error (non-TTY)`.
- `hydrate/` -- reads a single boundary/cassette record on stdin, atomically installs the cassette under `~/.claude/projects/<slug>/<new-uuid>.jsonl`, then runs `claude --resume <new-uuid>`; cost-preview gate, plan-overrun rejection (exit 5, override via `--force-plan-overrun`), CC version compat (exit 8, override via `--force-cross-version-fork`).

Tests:
- 108 automated tests across `tests/unit/` (slug, jsonl_search, boundaries, cost, config, cc_compat, errors, schema) and `tests/integration/` (search-then-fork pipeline, cassette sidecars, pipeline fan-in rejection); additional env-gated manual tests under `tests/manual/`.
- Synthetic 20-turn JSONL fixture at `tests/fixtures/synthetic_session.jsonl` with deterministic UUIDs, parentUuid chain, one compact boundary at line 10, two sidechain entries, one tool-use turn.
- Manual gate scaffolding directory at `tests/manual/` (env-gated by `CCIPC_RUN_REAL_CC_TESTS=1`); the gate procedures themselves -- JSONL-unknown-fields parser tolerance, slug equality vs real `~/.claude/projects/`, full e2e hydrate against `claude --resume` -- are documented as steps in the public test checklist.
- End-to-end smoke at `tests/one-offs/smoke_pipeline.py`.

Test infrastructure:
- Public human test checklist at `tests/checklists/v0.1.0__Phase1__search-then-fork-poc.md` (HV smoke section + 7 detailed sections, cross-shell command forms for cmd/PowerShell/POSIX).
- Tester-agent static-analysis report at `tests/checklists/v0.1.0__Phase1__search-then-fork-poc__results.md` (produced when sub-agent shell permissions blocked execution-mode runs).

Documentation:
- `docs/concepts.md` -- boundaries, headroom, cassettes, plan-aware costing, the compaction circuit-breaker.
- `docs/cookbook.md` -- five worked examples (basic, AND-search, type filter, headroom override, pre-compact opt-in).
- `docs/troubleshooting.md` -- every exit code with trigger condition, error text, and recovery commands.

### Changed
- `kits/core.kit.json` description and tool list updated to reflect the real Phase 1 toolset (5 tools); old `search-multi` placeholder entry removed from the kit declaration.
- `src/ccipc/cli.py` help formatter is now terminal-width-aware (`shutil.get_terminal_size`), with a 30-col floor for narrow terminals and an 80-col fallback when stdout is not a TTY (replaces the previous hardcoded 56-col column that truncated on wide terminals).
- `src/ccipc_lib/__init__.py` re-exports `BASE_VERSION` and `DISPLAY_VERSION` alongside `__version__`, `__app_name__`, `PIP_VERSION` for convenience.
- `README.md` minor copy edits; pre-alpha badge removed.
- `.gitignore` adds `.claude/` so project-scoped Claude Code permissions stay out of public history.

### Fixed
- `tools/core/cassette/cassette.py:_build_cassette_jsonl` now writes its temp file next to the target (not next to the source). The previous behavior could fail with `OSError` on `os.replace` when source and target lived on different volumes (Windows). Adds two-layer cleanup: `BaseException`-scoped `tmp.unlink()` during build, plus `OSError`-scoped cleanup if `os.replace` itself fails.
- `src/ccipc_lib/errors.py` -- `TargetCollisionError` recovery hint generalized from "Re-run hydrate" to "Re-run the operation" (the same error is raised by cassette).
- `src/ccipc_lib/errors.py` -- `NoMatchesError` now carries a `why=` field, matching the convention used by other `CCIPCError` subclasses.

### Notes
- All Phase 1 functionality is implemented and 108/108 unit + integration tests are green, but three manual gates (Section 6.1 JSONL-unknown-fields parser tolerance; HV.4 slug equality on real `~/.claude/projects/`; full e2e hydrate against `claude --resume`) must pass before tagging v0.1.0.
- Project-scoped Claude Code permissions live at `.claude/settings.json` (now gitignored). Permissions are loaded at session-init only -- changes require restarting Claude Code to take effect.
- Phase 1.5 (windowed cassette mode + world coordinates + `cc_token_math` port) is designed but not implemented; see `private/claude/2026-04-29__20-55-42__windowed-cassette-mode-design.md` and the supporting investigation note `private/claude/notes/cli/2026-04-29__cc-context-extraction-investigation.md`.
- Issue #11 opened for a future semantic-search modality that uses Claude Code itself as a candidate ranker.

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

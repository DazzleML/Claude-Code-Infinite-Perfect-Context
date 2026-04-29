# Platform Support

`ccipc` is designed to work across Windows, Linux, and macOS. The framework itself is pure Python (3.10+) with `dazzlecmd-lib` as the only required runtime dependency. Most platform variability comes from external integrations (`csb`'s git history, Claude Code's session directory layout, the `claude` CLI itself).

## Framework Support

| Component | Windows | Linux | macOS |
|-----------|---------|-------|-------|
| `ccipc` CLI dispatcher | Tested | Expected | Expected |
| Aggregator tool discovery | Tested | Expected | Expected |
| Project root resolution | Tested | Expected | Expected |
| Version sync hooks | Tested | Expected | Expected |

## Tool Support (Phase 1 POC scope)

| Tool | Windows | Linux | macOS | Notes |
|------|---------|-------|-------|-------|
| `search` | Planned | Planned | Planned | Pure Python, JSONL parsing -- portable |
| `find-boundary` | Planned | Planned | Planned | Pure Python -- portable |
| `cassette` | Planned | Planned | Planned | Pure Python -- portable |
| `cost-estimate` | Planned | Planned | Planned | Pure Python -- portable |
| `hydrate` | Planned | Planned | Planned | Shells out to `claude --resume`; depends on Claude Code being installed |

## External Integrations

| Integration | Status | Platform notes |
|-------------|--------|----------------|
| Claude Code (`claude` CLI) | Required | Cross-platform; ccipc shells out to it |
| `csb` (Claude-Session-Backup) | Required for multi-session search (Phase 2+) | Windows-tested; csb is pure Python with `git` |
| `~/.claude/projects/` layout | Required | Same path on all OSes (`%USERPROFILE%` / `$HOME` resolves) |
| `dazzlecmd-lib` | Required | Pure Python -- portable |

## Path Handling

`ccipc` uses Python's `pathlib` and `os.path` throughout. Forward and backward slashes are normalized internally. The synthetic JSONL paths it writes always go under `~/.claude/projects/<slug>/<custom-id>.jsonl`, which Claude Code resolves consistently across platforms.

## Known Constraints

- **Pre-Alpha**: tooling is scaffolding only. Phase 1 POC is the first functional release.
- **No Windows-specific code paths** are anticipated -- if any are needed, they will be wrapped behind feature detection (e.g., junction support for cassette caches).
- **Bash vs PowerShell**: the CLI is shell-agnostic. Pipeline composition (`ccipc A | ccipc B | ccipc C`) works in both.

## Reporting Issues

If `ccipc` doesn't behave as expected on your platform, please file an issue at [github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/issues](https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context/issues) including:
- OS and version
- Python version
- Output of `ccipc --version` and `ccipc list`
- The command and full error message

# Troubleshooting

Every common ccipc failure mode is self-documenting — the error tells you WHAT, WHY, and WHAT TO DO. This page is the canonical exit-code catalog and recovery cookbook for when those errors aren't enough on their own.

---

## Exit codes

| Code | Class | Meaning | Tools that emit it |
|------|-------|---------|--------------------|
| 0 | OK | Success | all |
| 1 | `CLIUsageError` / `SessionNotFoundError` | Bad CLI args, or session not findable | all |
| 2 | `NoMatchesError` | Search returned zero hits | search, find-boundary |
| 3 | `CorruptJSONLError` | A JSONL line failed to parse | search, find-boundary |
| 4 | `CostPreviewRejectedError` | User answered "no" at the gate | hydrate |
| 5 | `PlanBudgetExceededError` | Cassette exceeds 5h plan window | hydrate |
| 6 | `TargetCollisionError` | Cassette path already exists | cassette, hydrate |
| 7 | `PipelineFanInError` | Single-target tool got >1 stdin record | cassette, hydrate |
| 8 | `CCVersionIncompatibleError` | Cassette CC version doesn't match installed | hydrate |
| 9 | `ConfigError` | `~/.claude/ccipc/config.toml` missing or malformed | cost-estimate, hydrate |
| 99 | `HydrateLaunchError` (and other internal) | `claude --resume` failed to launch | hydrate |

---

## Recovery recipes

### Exit 1 — Could not find that session

```
Error: could not find that session
  Session id: 019f1e2d-4919-4a7d-a52f-2ef9f83f5ef7
  Searched: /Users/me/.claude/projects/...
```

Causes & fixes:
- **Session was deleted** — restore from csb if backed up: `csb restore 019f1e2d-...`
- **Session was archived** — list active sessions: `claude --list`
- **Wrong UUID** — search backups: `csb search "<keyword from the session>"`
- **Cross-machine UUID** — sessions don't roam between hosts; UUIDs aren't portable.

### Exit 2 — No matches found

```
Error: no matches found
  Search terms: needle1 AND needle2
  Session: 019f1e2d-...
```

Fixes:
- Try fewer or more general terms
- Drop `--type` to search all message types
- Verify the session has the expected content: `head -n 50 <jsonl-path>`

### Exit 3 — Malformed JSONL

```
Error: encountered malformed JSONL
  File: /Users/me/.claude/projects/.../<uuid>.jsonl
  Line: 4231
  Parse error: Expecting value
```

This means the source session JSONL has a corrupted line — usually from an interrupted write or a power loss during a session. Recovery:

```bash
# Find an earlier git commit of the session via csb
csb show 019f1e2d-... --commits  # or your csb's equivalent
csb restore 019f1e2d-... --commit <prior-hash>

# Or skip the corrupt line and search the rest:
ccipc search ... --on-corrupt skip   # default; emits warning to stderr
```

### Exit 4 — Cost preview rejected

You answered "no" at the y/n prompt. No state was changed. Re-run when ready, or refine your search to a smaller cassette first.

### Exit 5 — Plan budget exceeded

```
Error: cassette exceeds plan budget
  Plan: max5
  Plan 5h budget: 88,000 tokens
  Cassette size:  100,234 tokens (113.9% of budget)
```

This cassette is bigger than your 5-hour quota window. Forking into it would consume your entire budget AND THEN SOME — you'd be rate-limited the moment you tried to do anything in the new session. Fixes:

- Increase `--headroom-tokens` to make the cassette smaller (rewinds you less far back, but still gets you past the relevant turn).
- Refine your search to a later hit closer to your needle (less cassette to copy).
- Pass `--force-plan-overrun` if you accept being rate-limited mid-session.

### Exit 6 — Target collision

```
Error: target path already exists
  Target: /Users/me/.claude/projects/<slug>/<uuid>.jsonl
```

Astronomically unlikely (UUIDv4 collision is 1 in 5×10^36). If you see this:

- Re-run hydrate; a fresh UUID will be generated
- Or check if a previous hydrate left a stale cassette that you may want to clean up: `ls ~/.claude/projects/<slug>/`

### Exit 7 — Pipeline fan-in violation

```
Error: received multiple input records on stdin
  Tool 'cassette' is single-target but stdin has 5 records.
```

`cassette` and `hydrate` are single-target operations; `search` and `find-boundary` may emit many candidates. Pick one:

```bash
# Take the first hit
ccipc search ... | ccipc find-boundary | head -n 1 | ccipc cassette ...

# Pick by line number
ccipc search ... | ccipc find-boundary | jq 'select(.line_num == 4231)' | ccipc cassette ...

# Use a more specific search to narrow to one hit
ccipc search ... --term "very specific phrase" | ...
```

### Exit 8 — CC version incompatible

```
Error: cassette is incompatible with your Claude Code version
  Cassette CC version: 2.4.0
  Current CC version:  2.5.1
```

This is good — it caught a potential corruption. Options:

- **Cassette older than installed**: ccipc shouldn't refuse this case (forward-minor compatibility). If it does, file a bug.
- **Cassette newer than installed**: upgrade Claude Code with `npm install -g @anthropic-ai/claude-code` (or your install method).
- **Different major version**: a schema may have broken. Building a fresh cassette from your CURRENT session is the safe path.
- **Force**: pass `--force-cross-version-fork` only if you know what you're doing. Cassette may fail silently or corrupt the new session.

### Exit 9 — Config error

```
Error: ccipc config issue
  Config: /Users/me/.claude/ccipc/config.toml
  missing required key: plan
```

ccipc needs to know your plan to surface the right cost warnings. Fixes:

```bash
# Run any ccipc command interactively -- you'll be prompted once
ccipc cost-estimate --cassette /tmp/x.jsonl

# Or write the config manually
mkdir -p ~/.claude/ccipc
cat > ~/.claude/ccipc/config.toml <<EOF
config_version = 1
plan = "max5"
default_headroom_tokens = 25000
EOF

# Or pass --plan per-invocation (doesn't write config)
ccipc cost-estimate --cassette /tmp/x.jsonl --plan max5
```

### Exit 99 — claude --resume failed to launch

```
Error: claude --resume failed to launch
  Cassette: /Users/me/.claude/projects/<slug>/<uuid>.jsonl
  Session UUID: abc-123
```

The cassette was written successfully but `claude --resume` failed to start. Common causes:

- **`claude` not on PATH**: install/reinstall the CLI
- **Cassette schema rejected**: try `--no-inline-meta` to skip the `ccipc_meta` injection
- **Network/auth issue**: run `claude --status` to check
- **CC version actually mismatched** (despite the compat check): see exit 8

Manual recovery:
```bash
claude --resume <uuid-from-error>

# To clean up a botched cassette:
rm ~/.claude/projects/<slug>/<uuid>.jsonl
rm ~/.claude/session-states/<uuid>.json
rm ~/.claude/session-states/<uuid>.name-cache
rm ~/.claude/session-states/<uuid>.source
```

---

## Diagnostic flags

Useful when something behaves unexpectedly:

| Flag | Tool | Effect |
|------|------|--------|
| `--on-corrupt raise` | search, find-boundary | Don't silently skip malformed JSONL — fail loudly with line number |
| `--include-pre-compact` | find-boundary | Walk past `SystemCompactBoundaryMessage` lines |
| `--no-inline-meta` | cassette | Skip the `ccipc_meta` injection on first user-message line |
| `--no-claude-launch` | hydrate | Install the cassette but don't actually run `claude --resume` (use to inspect cassette before committing) |
| `--quiet` | cost-estimate | Suppress stderr human-readable preview; only emit JSONL on stdout |

## Common gotchas

- **`claude --list` doesn't show ccipc forks immediately** — CC's session list is cached; the new session UUID will appear after CC's next refresh.
- **Cassette file size is small but token estimate is large** — token estimation is `bytes / 2`, which assumes ASCII-heavy text. UTF-8 multibyte content gets over-estimated. The estimate is conservative by design.
- **Pipeline output looks like garbage** — likely you're catting JSONL records to a terminal that's wrapping them. Pipe to `jq .` for pretty-printing: `... | jq .`
- **`ccipc list` doesn't show all tools** — verify the kit manifest at `kits/core.kit.json` declares all 5 tools, and each tool has its `.ccipc.json` manifest.

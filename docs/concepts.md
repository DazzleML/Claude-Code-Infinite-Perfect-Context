# Concepts

ccipc is a power tool. The mental model is small but non-obvious. This page explains the four ideas you need to use it confidently: **boundaries**, **headroom**, **cassettes**, and **plan-aware cost**. Read once, refer back when something surprises you.

---

## What ccipc actually does

Claude Code ("CC") session transcripts live as JSONL files at `~/.claude/projects/<project-slug>/<session-uuid>.jsonl`. Each line is one turn (user message, assistant response, tool use, tool result, or a system marker like a compaction boundary). When CC compacts, it summarizes most of the conversation away — your "current" session loses access to the verbatim history.

ccipc does **reverse compaction**: it reads a past session JSONL, walks back to a clean turn boundary, copies the verbatim prefix into a synthetic JSONL with a fresh session UUID ("the cassette"), installs that JSONL where CC expects to find sessions, and runs `claude --resume` so you land in the past with full pre-compaction fidelity. The original session is untouched.

The pipeline is composable, Unix-style:

```bash
ccipc search --session <id> --term "X"      \
  | ccipc find-boundary --before              \
  | ccipc cassette --mode A                   \
  | ccipc cost-estimate                       \
  | ccipc hydrate
```

Each stage emits one JSONL record per result on stdout, enriched with new fields by each subsequent stage (flat-merge — upstream fields are preserved).

---

## Boundaries

A **boundary** is the JSONL line where the cassette's verbatim prefix ENDS. ccipc walks backward from your search hit to the nearest line satisfying:

- `type == "user"` (a user turn)
- `isSidechain == False` (not an inner agent-to-agent call)
- The line is not after a `SystemCompactBoundaryMessage` you're hard-stopping at

Why a clean user-turn? Because the cassette must end in a state CC's parser will accept on resume. Cutting off mid-tool-use breaks that, sometimes silently. Cutting at a user turn means the next thing CC sees is your fresh prompt.

### Compaction boundaries are hard stops by default

If a `SystemCompactBoundaryMessage` line sits between your search hit and the most recent user turn before it, ccipc treats that compact line as a **hard stop**. The boundary becomes the compact line itself, not a pre-compaction user turn. This is intentional: walking past a compact would re-include content CC explicitly summarized away, defeating the point.

Override with `--include-pre-compact` if you specifically want to recover pre-compacted content. Use sparingly — that content was summarized for a reason.

---

## Headroom

A cassette consumes tokens from your context window the moment you `claude --resume` it. If the cassette is too big, CC's auto-compaction will trigger on the **first** turn of your new session, possibly before you've done anything useful. Worse: if compaction itself fails (which it can, particularly on near-limit cassettes), CC's circuit breaker (3 consecutive failures) **permanently breaks** the session.

So we leave room. The `--headroom-tokens N` flag tells `find-boundary` "don't pick a boundary so far back that the cassette consumes within N tokens of the autocompact threshold." Larger N → smaller cassette → more room for new turns, less verbatim history.

**Plan-aware defaults** because plan budgets differ wildly:

| Plan | 5h budget (approx) | Default headroom | Why |
|------|--------------------|--------------------|-----|
| `max5`  | ~88K tokens   | 25K | Tight budget, can't afford big cassettes |
| `max20` | ~220K tokens  | 50K | More headroom, more breathing room |
| `api`   | unbounded     | 30K | API users care about compaction, not 5h |
| `1m`    | unbounded     | 50K | 1M-context, but compaction loops are catastrophic |

Override per-invocation with `--headroom-tokens N`.

---

## Cassettes

A **cassette** is the synthetic JSONL prefix written by `ccipc cassette`. It's a verbatim copy of the source JSONL up to and including the boundary line, with these surrounding artifacts:

```
~/.claude/projects/<slug>/<new-uuid>.jsonl     ← the cassette itself
~/.claude/session-states/<new-uuid>.json       ← state metadata + ccipc lineage
~/.claude/session-states/<new-uuid>.name-cache ← "Fork of <orig-name>"
~/.claude/session-states/<new-uuid>.source     ← "ccipc-fork"
```

CC uses the `.json` sidecar to resolve the session, the `.name-cache` for display, and the `.source` to know how the session was created. The `.run` and `.started` runtime markers are CC's to write — ccipc never touches them.

### Modes

- **Mode A** (Phase 1, the only mode in v0.1) — verbatim past. The cassette is byte-identical to the source up to the boundary. No summarization, no synthesis. Modified only by an injected `ccipc_meta` field on the first user-message line (for self-describing cassettes; pass `--no-inline-meta` to skip).
- **Mode B** (Phase 3, not in v0.1) — past + summarized present. Cassette is verbatim past PLUS an AI-generated summary of "what we were doing" before the rewind, appended at the tail.

---

## Plan-aware cost

API price is the wrong signal for most users. If you're on Max5, a $0.30 cassette is irrelevant — what matters is that it consumes 95% of your 5h budget, leaving you nothing for the rest of the day's work.

`ccipc cost-estimate` shows the **plan-aware view first**:

```
─── ccipc cost preview ───────────────────────────────────────────
  Plan:       max5 -- 47.3% of 5h budget (41,612 / 88,000 tokens)
  API cost:   $0.1248 (41,612 input tokens @ claude-sonnet-4-5, ...)
  Model:      claude-sonnet-4-5 (source: default)
  [HIGH] Cassette is within 10% of the autocompact threshold; ...
    other plan max20: 18.9% (220,000 budget)
──────────────────────────────────────────────────────────────────
```

`ccipc hydrate` enforces:

- **Plan-overrun rejection** (exit 5): if the cassette exceeds the user's 5h budget, hydrate refuses unless `--force-plan-overrun` is passed.
- **Cost-preview gate**: interactive y/n prompt by default; `--yes` skips, but only if `CCIPC_ALLOW_AUTOHYDRATE=1` env var is set OR stdin is a TTY. This prevents agent-driven workflows from silently spending without user intent.

### The compaction circuit-breaker risk

CC has `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3` (verified empirically in `services/compact/autoCompact.ts`). After three failed compactions in a single session, CC stops trying — the session is permanently broken. A cassette that triggers compaction on its first turn AND fails to compact (e.g., because the "summarize prompt" itself doesn't fit) can permanently break the new session. Conservative headroom defaults exist for this reason. **Don't trim them aggressively unless you know what you're doing.**

---

## Why `~/.claude/ccipc/` (not XDG)

ccipc state (config, future quota ledger) lives at `~/.claude/ccipc/config.toml` rather than `~/.config/ccipc/`. Reasons:

1. **Discoverability**: users already know `~/.claude/` is where Claude state lives. Putting ccipc state next to it is findable.
2. **Cross-platform consistency**: `~/.claude/` resolves identically on Windows, macOS, Linux. XDG conventions vary.
3. **Co-location with what we read from**: ccipc reads `~/.claude/projects/` and `~/.claude/session-states/` — its own config sits next to those.

This decision is documented in the master plan. If CC ever cleans up unknown subdirectories of `~/.claude/`, we'll add a backup-restore mechanism.

---

## Slug derivation

The "project slug" used for `~/.claude/projects/<slug>/` is computed by:

```
canonical = realpath(cwd) + NFC-normalize
slug = canonical.replace(/[^a-zA-Z0-9]/g, '-')
if len(slug) > 200: slug = slug[:200] + '-' + djb2_hash(canonical, base36)
```

This matches CC's `sanitizePath` in `utils/sessionStoragePortable.ts` exactly for short paths. For paths > 200 chars, CC's runtime uses Bun.hash (wyhash) while ccipc's Python uses djb2 — but CC's `findProjectDir` has a prefix-fallback that tolerates this mismatch. So your cassette will land in the right project directory regardless.

---

## Soft-touch invariants (cross-cutting)

ccipc never modifies your existing data:

- All reads from csb's index and from CC's state are **read-only**.
- All writes go to `~/.claude/projects/<slug>/<NEW-uuid>.jsonl` and `~/.claude/session-states/<NEW-uuid>.*` — never the source session's UUID-keyed files.
- Cassette content is byte-identical to source modulo the optional `ccipc_meta` injection.
- The original session JSONL's checksum is unchanged after a pipeline run.
- csb's SQLite row count is unchanged.

If a ccipc invocation ever corrupts source state, that's a bug. File an issue.

# Cookbook

Five worked examples for common ccipc workflows. Each example shows the full command, what each stage does, and what the output looks like.

---

## Example 1: Basic single-term search → fork

You remember writing some Python code involving "websocket reconnection" three sessions ago, but the current session has compacted past it. You want to rewind into that conversation.

```bash
# Step 1: locate the session id (csb is great for this)
csb search "websocket"
#   Found 1 session matching 'websocket':
#     019f1e2d-... (24 days ago, "C:\code\my-app")

# Step 2: fork into the session at the relevant turn
ccipc search --session 019f1e2d-4919-4a7d-a52f-2ef9f83f5ef7 \
    --term "websocket reconnection" \
  | ccipc find-boundary --before \
  | ccipc cassette --mode A \
  | ccipc cost-estimate \
  | ccipc hydrate
```

What happens:
1. `search` scans the JSONL for "websocket reconnection" → emits hits as JSONL.
2. `find-boundary` walks back to the user turn that started the topic.
3. `cassette` writes the verbatim prefix as a new JSONL.
4. `cost-estimate` shows you "23.4% of your max5 5h budget" or similar.
5. `hydrate` prompts y/n, then runs `claude --resume` and you're in.

---

## Example 2: AND-search across multiple terms

You wrote a function that mentions both "lossy" and "demo gif" — search for the line that has both.

```bash
ccipc search --session 019f1e2d-... \
    --term "lossy" \
    --term "demo gif" \
    --type assistant
```

`--term` is repeatable; every term must appear in the same line for the line to match (case-insensitive). `--type assistant` filters to assistant turns only — useful when you remember Claude WROTE something and don't want noise from your own user messages mentioning the words.

---

## Example 3: Filtering by message type (`--type`)

Find every user turn that mentioned "API key" — searching only YOUR side of the conversation.

```bash
ccipc search --session 019f1e2d-... \
    --term "API key" \
    --type user \
    --limit 50
```

Valid `--type` values: `user`, `assistant`, `system`, `attachment`. Note that `tool_use` and `tool_result` are **nested inside assistant `message.content`** — they're not top-level types. Search for tool calls by filtering `--type assistant` and adding the tool name as a term.

---

## Example 4: Custom headroom override

You're on Max5 (~88K 5h budget) and you want a *bigger* cassette than the default 25K headroom. You know you'll be making just a couple of additional turns and want maximum verbatim past.

```bash
ccipc search --session 019f1e2d-... --term "the topic" \
  | ccipc find-boundary --before --headroom-tokens 8000 \
  | ccipc cassette --mode A \
  | ccipc cost-estimate \
  | ccipc hydrate
```

`--headroom-tokens 8000` reserves only 8K tokens for new turns — leaving up to 80K for the cassette. Cost preview will warn you that you're close to the autocompact threshold. Watch for the `[HIGH]` warning in the cost preview.

If the cassette would exceed your 5h budget entirely, `hydrate` exits 5 (`PlanBudgetExceededError`). Pass `--force-plan-overrun` to bypass — you'll be rate-limited mid-session and accept that.

---

## Example 5: Skipping a compaction boundary

By default, ccipc treats `SystemCompactBoundaryMessage` lines as hard stops — it won't include pre-compacted content in the cassette. But sometimes you specifically want to recover content from before a compaction event.

```bash
ccipc search --session 019f1e2d-... --term "the missing context" \
  | ccipc find-boundary --before --include-pre-compact \
  | ccipc cassette --mode A \
  | ccipc cost-estimate \
  | ccipc hydrate
```

`--include-pre-compact` lets `find-boundary` walk past compact lines. The resulting cassette will include content CC explicitly summarized away. Use this when:

- The information you need wasn't preserved in the compaction summary
- You're willing to spend tokens to re-load context CC tried to elide
- You understand the cassette will be larger than usual

If there are MULTIPLE compactions between your search hit and the start of the session, you can chain `--include-pre-compact` walks: first walk past compact #1, then walk past compact #2, etc. The flag opts in to crossing all compaction boundaries.

---

## Bonus: standalone (no piping) usage

Each tool also accepts direct args for testing or scripting:

```bash
# Search standalone
ccipc search --session /path/to/session.jsonl --term "X"

# Find boundary standalone (no upstream search)
ccipc find-boundary --jsonl /path/to/session.jsonl --line 4231 \
    --headroom-tokens 25000

# Cassette standalone
ccipc cassette --mode A \
    --jsonl /path/to/session.jsonl \
    --boundary-line 4180 \
    --boundary-uuid msg-uuid-here \
    --output /tmp/my-cassette.jsonl

# Cost estimate from a file
ccipc cost-estimate --cassette /tmp/my-cassette.jsonl --plan max5

# Hydrate from a file
ccipc hydrate --cassette /tmp/my-cassette.jsonl
```

All tools emit JSONL on stdout regardless of how they're invoked, so you can mix-and-match piping with file-based input.

"""Verified Claude Code constants used by ccipc.

Every value here was extracted by direct read of the bundled Claude Code
source at C:\\code-ext\\claude-code\\ during the Phase 1 design pass
(see private/claude/2026-04-29__07-00-36__DISCUSS_Rnd4_FINAL_ASSESSMENT_*).

The source-path comments are load-bearing: when a CC update bumps these,
`ccipc check-drift` (a dev-only tool) re-extracts them from the on-disk
TS files and diffs against this manifest. If the diff is non-empty, the
manifest needs a new version block.

Do NOT compute these values dynamically -- they're declared so that the
ccipc behavior on user machines does not depend on having CC source
installed alongside ccipc.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Compaction thresholds -- services/compact/autoCompact.ts
# ---------------------------------------------------------------------------

#: Reserved tokens for the compact-summary output.
#: services/compact/autoCompact.ts:30
MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000

#: Subtracted from effective context window to derive the autocompact threshold.
#: services/compact/autoCompact.ts:62
AUTOCOMPACT_BUFFER_TOKENS = 13_000

#: Subtracted to derive the warning threshold (where CC starts nagging).
#: services/compact/autoCompact.ts:63
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000

#: Subtracted to derive the error threshold.
#: services/compact/autoCompact.ts:64
ERROR_THRESHOLD_BUFFER_TOKENS = 20_000

#: Subtracted from effective context window to derive the HARD blocking limit.
#: Below this margin the API call will be refused.
#: services/compact/autoCompact.ts:65
MANUAL_COMPACT_BUFFER_TOKENS = 3_000

#: Hardcoded circuit-breaker. After this many consecutive autocompact failures
#: in a single session, CC stops trying. The session is then permanently
#: broken. A "hot" cassette can trip this on the FIRST request after hydrate.
#: services/compact/autoCompact.ts:70
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3

# ---------------------------------------------------------------------------
# Slug / sanitizePath -- utils/sessionStoragePortable.ts
# ---------------------------------------------------------------------------

#: Maximum length of a filesystem-safe sanitized path component before
#: a hash suffix is appended for uniqueness. Most filesystems limit
#: components to 255 bytes; CC uses 200 to leave room for the hash.
#: utils/sessionStoragePortable.ts:293
MAX_SANITIZED_LENGTH = 200

#: Regex used to strip non-alphanumeric characters from paths when
#: building the project-directory name under ~/.claude/projects/.
#: utils/sessionStoragePortable.ts:312
SANITIZE_PATH_PATTERN = r"[^a-zA-Z0-9]"

#: The replacement character. Becomes the run-on hyphens in slugs like
#: "C--code-wtf-restarted".
SANITIZE_PATH_REPLACEMENT = "-"

# ---------------------------------------------------------------------------
# Token estimation -- matches CC's heuristic of "len_bytes / 2"
# ---------------------------------------------------------------------------

#: Bytes-per-token divisor used by CC's lightweight token-counting heuristic.
#: This is intentionally crude; for real cost, anthropic's token-count API
#: is more accurate but we don't want a network round-trip on every estimate.
TOKEN_HEURISTIC_BYTES_PER_TOKEN = 2

# ---------------------------------------------------------------------------
# Claude Code context windows by model
# ---------------------------------------------------------------------------
# These mirror getContextWindowForModel() defaults. The 1M window for Opus
# requires the [1m] beta header (getSdkBetas() controls this).

CONTEXT_WINDOW_DEFAULT = 200_000
CONTEXT_WINDOW_1M_BETA = 1_000_000

#: Map from model-id-or-alias to its context window. Used when --model
#: is not specified and we need to default. Conservative: when unsure,
#: assume 200K.
MODEL_CONTEXT_WINDOWS = {
    # Anthropic
    "claude-sonnet-4-5": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-opus-4-6": 200_000,
    "claude-opus-4-7": 200_000,
    "claude-opus-4-7[1m]": 1_000_000,
    "claude-haiku-4-5": 200_000,
    # Aliases CC accepts
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
}

#: Default model-id when nothing is specified by --model or ANTHROPIC_MODEL.
DEFAULT_MODEL = "claude-sonnet-4-5"

# ---------------------------------------------------------------------------
# Plan-aware quotas (per public reports; verify before docs go live)
# ---------------------------------------------------------------------------
# These numbers come from public reports on Anthropic's Max plans. Subject
# to change. Conservative defaults are used so we err on the side of warning
# users rather than silently over-promising.

PLAN_QUOTAS_5H_TOKENS = {
    "max5": 88_000,
    "max20": 220_000,
    "api": None,        # No 5h cap; we still warn at autocompact threshold
    "1m": None,         # 1M-context users are typically API; no 5h cap modeled
}

#: Plan-aware default headroom (tokens) used by find-boundary when picking
#: where to rewind to. Smaller plans need tighter headroom because their
#: total budget is smaller; bigger plans can afford more conservative.
PLAN_DEFAULT_HEADROOM_TOKENS = {
    "max5": 25_000,
    "max20": 50_000,
    "api": 30_000,
    "1m": 50_000,
}

VALID_PLANS = ("max5", "max20", "api", "1m")

# ---------------------------------------------------------------------------
# Pricing constants (USD per 1M tokens, as of 2026-04-29)
# ---------------------------------------------------------------------------
# Source: https://www.anthropic.com/pricing -- check before each release.
# These are INPUT prices only; cassette tokens are billed as input. Output
# is incurred during the post-hydrate session, which is variable and not
# part of the cassette cost.

PRICING_INPUT_USD_PER_M = {
    "claude-sonnet-4-5": 3.00,
    "claude-sonnet-4-6": 3.00,
    "claude-opus-4-5": 15.00,
    "claude-opus-4-6": 15.00,
    "claude-opus-4-7": 15.00,
    "claude-opus-4-7[1m]": 30.00,    # 1M-context tier doubles per-token pricing
    "claude-haiku-4-5": 0.80,
    "sonnet": 3.00,
    "opus": 15.00,
    "haiku": 0.80,
}
PRICING_AS_OF = "2026-04-29"

# ---------------------------------------------------------------------------
# JSONL line types -- per CC's isTranscriptMessage() in services/transcripts/
# ---------------------------------------------------------------------------
# Note: tool_use and tool_result are NESTED inside assistant message.content,
# they are NOT top-level types. The placeholder search-multi tool had this
# wrong before correction.

VALID_TRANSCRIPT_TYPES = ("user", "assistant", "system", "attachment")

#: Special marker indicating a compaction boundary in the JSONL. find-boundary
#: must hard-stop at these unless --include-pre-compact is passed.
SYSTEM_COMPACT_BOUNDARY_TYPE = "SystemCompactBoundaryMessage"

# ---------------------------------------------------------------------------
# CC config / state directories
# ---------------------------------------------------------------------------

#: Subdirectory under ~/.claude/ that holds session JSONLs, partitioned by
#: project slug. Format: ~/.claude/projects/<slug>/<uuid>.jsonl
CC_PROJECTS_SUBDIR = "projects"

#: Subdirectory under ~/.claude/ that holds session-state sidecar files.
#: Each session has multiple sidecar files (json, name-cache, source) plus
#: optional run/started markers while the session is active.
CC_SESSION_STATES_SUBDIR = "session-states"

#: Sidecar file extensions the cassette tool MUST write.
CASSETTE_REQUIRED_SIDECAR_EXTS = (".json", ".name-cache", ".source")

#: Sidecar file extensions that CC writes itself when a session is active.
#: ccipc must NEVER write these -- they are runtime markers.
CC_RUNTIME_ONLY_SIDECAR_EXTS = (".run", ".started")

# ---------------------------------------------------------------------------
# Manifest version
# ---------------------------------------------------------------------------
# Bump this when constants are updated for a new CC version. Used by
# ccipc check-drift to know when the manifest itself needs review.

CC_CONSTANTS_MANIFEST_VERSION = "1.0"
CC_CONSTANTS_VERIFIED_AGAINST_CC_VERSION = "2.x"
CC_CONSTANTS_VERIFIED_DATE = "2026-04-29"
CC_CONSTANTS_VERIFIED_BY = "/collaborate3 Round 2 empirical verification"


def get_effective_context_window(model: str) -> int:
    """Mirror of CC's getEffectiveContextWindowSize(model).

    Returns context_window - min(max_output, MAX_OUTPUT_TOKENS_FOR_SUMMARY).
    For practical purposes, since max_output is always >= 20K for current
    models, this simplifies to context_window - 20_000.

    Args:
        model: model id or alias (e.g. "claude-sonnet-4-5", "sonnet").

    Returns:
        The effective context window in tokens.
    """
    context_window = MODEL_CONTEXT_WINDOWS.get(model, CONTEXT_WINDOW_DEFAULT)
    return context_window - MAX_OUTPUT_TOKENS_FOR_SUMMARY


def get_autocompact_threshold(model: str) -> int:
    """Mirror of CC's getAutoCompactThreshold(model).

    Returns the token count at which CC will trigger an auto-compaction.

    Args:
        model: model id or alias.

    Returns:
        Threshold in tokens. effective_context_window - AUTOCOMPACT_BUFFER_TOKENS.
    """
    return get_effective_context_window(model) - AUTOCOMPACT_BUFFER_TOKENS


def get_blocking_limit(model: str) -> int:
    """Mirror of CC's hard blocking limit.

    Above this token count CC will refuse the API call entirely. Only
    MANUAL_COMPACT_BUFFER_TOKENS (3K) below the effective window.

    Args:
        model: model id or alias.

    Returns:
        Hard limit in tokens.
    """
    return get_effective_context_window(model) - MANUAL_COMPACT_BUFFER_TOKENS

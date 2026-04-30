"""Self-documenting errors for ccipc.

Each error class carries enough context to tell the user WHAT went wrong,
WHY (when known), and WHAT TO DO next. The 4-hour usability investment
from the Round 4 design pass: turn "broken" into "actionable".

All ccipc errors derive from CCIPCError. Tools catch CCIPCError at the
top of main() and emit the structured message to stderr, then exit with
the carried exit_code.

Pattern:

    try:
        do_thing()
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id, hint_command="csb search ...") from e
"""

from __future__ import annotations

import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Exit codes -- single source of truth, mirrored in docs/troubleshooting.md
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_CLI_USAGE = 1
EXIT_NO_MATCHES = 2
EXIT_CORRUPT_JSONL = 3
EXIT_COST_PREVIEW_REJECTED = 4
EXIT_PLAN_BUDGET_EXCEEDED = 5
EXIT_TARGET_COLLISION = 6
EXIT_PIPELINE_FAN_IN = 7
EXIT_CC_VERSION_INCOMPATIBLE = 8
EXIT_CONFIG_ERROR = 9
EXIT_INTERNAL = 99


class CCIPCError(Exception):
    """Base class for all ccipc errors.

    Carries enough context for tools to print a helpful message and
    exit with a specific exit code. Subclass this for new error categories
    rather than raising bare CCIPCError.
    """

    exit_code: int = EXIT_INTERNAL
    short_message: str = "ccipc encountered an unexpected error"

    def __init__(
        self,
        detail: str = "",
        *,
        why: Optional[str] = None,
        what_to_do: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ):
        self.detail = detail
        self.why = why
        self.what_to_do = what_to_do
        self.recovery_hint = recovery_hint
        super().__init__(self.formatted())

    def formatted(self) -> str:
        """Render a multi-line, user-facing error message."""
        lines = [f"Error: {self.short_message}"]
        if self.detail:
            lines.append(f"  {self.detail}")
        if self.why:
            lines.append(f"  Why: {self.why}")
        if self.what_to_do:
            lines.append(f"  What to do: {self.what_to_do}")
        if self.recovery_hint:
            lines.append(f"  Recovery: {self.recovery_hint}")
        return "\n".join(lines)


class CLIUsageError(CCIPCError):
    """Bad CLI flags / arguments. Exit 1."""

    exit_code = EXIT_CLI_USAGE
    short_message = "invalid command-line usage"


class SessionNotFoundError(CCIPCError):
    """Cannot locate the requested session. Exit 1."""

    exit_code = EXIT_CLI_USAGE
    short_message = "could not find that session"

    def __init__(self, session_id: str, *, searched_paths: Optional[list[str]] = None):
        detail = f"Session id: {session_id}"
        if searched_paths:
            detail += f"\n  Searched: {', '.join(searched_paths)}"
        super().__init__(
            detail,
            why="The session may have been deleted, archived, or never existed.",
            what_to_do=(
                "Check active sessions with: claude --list\n"
                "  Or search backups with: csb search '<keyword>'"
            ),
            recovery_hint=(
                "If the session was backed up by csb, try: csb restore <session-id>"
            ),
        )


class NoMatchesError(CCIPCError):
    """Search returned zero hits. Exit 2."""

    exit_code = EXIT_NO_MATCHES
    short_message = "no matches found"

    def __init__(self, terms: list[str], *, session_id: Optional[str] = None):
        detail = f"Search terms: {' AND '.join(terms)}"
        if session_id:
            detail += f"\n  Session: {session_id}"
        super().__init__(
            detail,
            why="No JSONL lines in this session contain all of the specified search terms.",
            what_to_do=(
                "Try fewer or more general terms.\n"
                "  Try --type to filter by message kind (user|assistant|system|attachment)."
            ),
        )


class CorruptJSONLError(CCIPCError):
    """JSONL line failed to parse. Exit 3."""

    exit_code = EXIT_CORRUPT_JSONL
    short_message = "encountered malformed JSONL"

    def __init__(
        self,
        path: str,
        line_num: int,
        *,
        parse_error: Optional[str] = None,
    ):
        detail = f"File: {path}\n  Line: {line_num}"
        if parse_error:
            detail += f"\n  Parse error: {parse_error}"
        super().__init__(
            detail,
            why="The session JSONL has a corrupted line, possibly from an interrupted write.",
            what_to_do=(
                "If this is a backup, restore from an earlier git commit:\n"
                "    csb restore <session-id> --commit <prior-hash>"
            ),
        )


class CostPreviewRejectedError(CCIPCError):
    """User answered 'no' at the cost-preview gate. Exit 4."""

    exit_code = EXIT_COST_PREVIEW_REJECTED
    short_message = "cost preview rejected"

    def __init__(self, estimated_cost_usd: float, estimated_tokens: int):
        super().__init__(
            f"Estimated: {estimated_tokens:,} tokens, ${estimated_cost_usd:.4f}",
            what_to_do=(
                "Re-run with --headroom-tokens larger to get a smaller cassette,\n"
                "  or refine your search to a later turn closer to the target."
            ),
        )


class PlanBudgetExceededError(CCIPCError):
    """Cassette exceeds the user's plan budget. Exit 5."""

    exit_code = EXIT_PLAN_BUDGET_EXCEEDED
    short_message = "cassette exceeds plan budget"

    def __init__(
        self,
        plan: str,
        plan_budget: int,
        cassette_tokens: int,
    ):
        pct = (cassette_tokens / plan_budget) * 100 if plan_budget else 0
        super().__init__(
            (
                f"Plan: {plan}\n"
                f"  Plan 5h budget: {plan_budget:,} tokens\n"
                f"  Cassette size:  {cassette_tokens:,} tokens ({pct:.1f}% of budget)"
            ),
            why=(
                "This cassette would consume more tokens than your plan's 5-hour\n"
                "  window allows, blocking all subsequent work in that window."
            ),
            what_to_do=(
                "Use a smaller cassette: --headroom-tokens larger, or fork to a\n"
                "  later turn closer to your target.\n"
                "  Or pass --force-plan-overrun to bypass this check (you'll be\n"
                "  rate-limited mid-session)."
            ),
        )


class TargetCollisionError(CCIPCError):
    """The target cassette path already exists. Exit 6."""

    exit_code = EXIT_TARGET_COLLISION
    short_message = "target path already exists"

    def __init__(self, target_path: str):
        super().__init__(
            f"Target: {target_path}",
            why="UUID collision (astronomically unlikely) or stale cassette.",
            what_to_do="Re-run the operation; a fresh UUID will be generated.",
        )


class PipelineFanInError(CCIPCError):
    """A single-target tool received >1 stdin record. Exit 7."""

    exit_code = EXIT_PIPELINE_FAN_IN
    short_message = "received multiple input records on stdin"

    def __init__(self, tool_name: str, record_count: int):
        super().__init__(
            f"Tool '{tool_name}' is single-target but stdin has {record_count} records.",
            why=(
                "search and find-boundary may emit many candidates, but cassette\n"
                "  and hydrate operate on exactly one target each."
            ),
            what_to_do=(
                "Refine your search, or pick one with: ... | head -n 1 | ccipc <tool>\n"
                "  Or use the search-then-fork wrapper which handles --pick selection."
            ),
        )


class CCVersionIncompatibleError(CCIPCError):
    """Cassette was made with a CC version not compatible with installed CC. Exit 8."""

    exit_code = EXIT_CC_VERSION_INCOMPATIBLE
    short_message = "cassette is incompatible with your Claude Code version"

    def __init__(
        self,
        cassette_cc_version: str,
        current_cc_version: str,
        *,
        cassette_path: Optional[str] = None,
    ):
        detail = (
            f"Cassette CC version: {cassette_cc_version}\n"
            f"  Current CC version:  {current_cc_version}"
        )
        if cassette_path:
            detail += f"\n  Cassette: {cassette_path}"
        super().__init__(
            detail,
            why=(
                "ccipc requires the cassette's major CC version to match yours,\n"
                "  and its minor version to be <= yours (so we don't try to use\n"
                "  a cassette built against a newer CC schema)."
            ),
            what_to_do=(
                "Upgrade Claude Code to match the cassette, or build a fresh\n"
                "  cassette from your current session.\n"
                "  Or pass --force-cross-version-fork to attempt anyway (may fail\n"
                "  silently or corrupt the new session)."
            ),
        )


class ConfigError(CCIPCError):
    """Config file missing or malformed. Exit 9."""

    exit_code = EXIT_CONFIG_ERROR
    short_message = "ccipc config issue"

    def __init__(
        self,
        detail: str,
        *,
        config_path: Optional[str] = None,
    ):
        if config_path:
            detail = f"Config: {config_path}\n  {detail}"
        super().__init__(
            detail,
            what_to_do=(
                "Run any ccipc command interactively to be prompted for setup,\n"
                "  or write the config manually:\n"
                "    mkdir -p ~/.claude/ccipc\n"
                "    echo 'config_version = 1' > ~/.claude/ccipc/config.toml\n"
                "    echo 'plan = \"max5\"' >> ~/.claude/ccipc/config.toml"
            ),
        )


class HydrateLaunchError(CCIPCError):
    """`claude --resume` failed to start. Exit 99 (internal/external)."""

    exit_code = EXIT_INTERNAL
    short_message = "claude --resume failed to launch"

    def __init__(
        self,
        cassette_path: str,
        new_uuid: str,
        *,
        subprocess_error: Optional[str] = None,
    ):
        detail = f"Cassette: {cassette_path}\n  Session UUID: {new_uuid}"
        if subprocess_error:
            detail += f"\n  Subprocess: {subprocess_error}"
        super().__init__(
            detail,
            what_to_do=(
                f"The cassette was written successfully. To retry manually:\n"
                f"    claude --resume {new_uuid}"
            ),
            recovery_hint=(
                f"If the cassette is unwanted, clean up:\n"
                f"    rm '{cassette_path}'\n"
                f"  And remove sidecar files at ~/.claude/session-states/{new_uuid}.*"
            ),
        )


def report_and_exit(err: CCIPCError) -> int:
    """Emit a CCIPCError to stderr in the standard format and return its exit code.

    Tools call this from main()'s top-level try/except. Returning instead of
    sys.exit-ing lets test harnesses inspect the exit code without process death.
    """
    print(err.formatted(), file=sys.stderr)
    return err.exit_code

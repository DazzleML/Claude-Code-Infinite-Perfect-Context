"""ccipc search -- single-session JSONL full-text search.

Usage:
    ccipc search --session <id-or-path> --term <text> [--term <text2> ...]
    ccipc search --session <id-or-path> --term <text> --type <user|assistant|system|attachment>

Outputs JSONL on stdout, one record per hit. Records flat-merge through
the pipeline; downstream tools (find-boundary, cassette, hydrate) add
their own fields without removing upstream ones.

The --all-sessions flag is reserved for Phase 2 (multi-session search).
In Phase 1 it raises NotImplementedError.

Examples:

    # Within a single session, find user turns mentioning "X"
    ccipc search --session 019f1e2d-... --term "needle" --type user

    # AND-search: every term must be present
    ccipc search --session 019f1e2d-... --term foo --term bar

    # Pipe through the rest of the pipeline
    ccipc search --session 019f1e2d-... --term "X" \\
        | ccipc find-boundary --before \\
        | ccipc cassette --mode A \\
        | ccipc hydrate
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# Path acrobatics for tool scripts: tools/core/<name>/script.py needs to
# import from src/ccipc_lib/. Walk up to find the project root and prepend
# src/ to sys.path. Mirrors wtf-windows' tool layout.
_HERE = Path(__file__).resolve().parent
for _ in range(5):
    candidate = _HERE / "src"
    if candidate.is_dir() and (candidate / "ccipc_lib").is_dir():
        sys.path.insert(0, str(candidate))
        break
    _HERE = _HERE.parent

from ccipc_lib import errors, jsonl_search, schema  # noqa: E402
from ccipc_lib.cc_constants import (  # noqa: E402
    CC_PROJECTS_SUBDIR,
    VALID_TRANSCRIPT_TYPES,
)
from ccipc_lib.tool_meta import get_description, load_tool_manifest  # noqa: E402

_MANIFEST = load_tool_manifest(__file__)
_OWN_DESCRIPTION = (
    "Single-session JSONL full-text search across a Claude Code "
    "session transcript."
)


def _resolve_session_path(session_arg: str) -> tuple[str, str]:
    """Resolve --session to a (session_id, jsonl_path) pair.

    Accepts:
        - A direct path to a .jsonl file
        - A bare UUID (looks up under ~/.claude/projects/*/<uuid>.jsonl)

    Args:
        session_arg: --session value provided on CLI.

    Returns:
        (session_id, absolute_jsonl_path)

    Raises:
        SessionNotFoundError: If neither resolution succeeds.
    """
    p = Path(session_arg)

    # If it's a direct file path that exists, use it.
    if p.is_file() and str(p).endswith(".jsonl"):
        return p.stem, str(p.resolve())

    # Otherwise treat it as a UUID and search ~/.claude/projects/*/<uuid>.jsonl.
    home = Path.home()
    projects_dir = home / ".claude" / CC_PROJECTS_SUBDIR
    if not projects_dir.exists():
        raise errors.SessionNotFoundError(
            session_arg,
            searched_paths=[str(projects_dir)],
        )

    # Walk every project directory looking for <uuid>.jsonl.
    matches: list[Path] = []
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        candidate = proj_dir / f"{session_arg}.jsonl"
        if candidate.is_file():
            matches.append(candidate)

    if not matches:
        raise errors.SessionNotFoundError(
            session_arg,
            searched_paths=[str(projects_dir)],
        )

    # Multiple matches across different project dirs would be highly
    # unusual; pick the largest (most-likely-real one) and warn.
    if len(matches) > 1:
        print(
            f"Warning: session id {session_arg} found in {len(matches)} project "
            f"directories; using the largest. To disambiguate, pass the full path.",
            file=sys.stderr,
        )
        matches.sort(key=lambda p: p.stat().st_size, reverse=True)

    chosen = matches[0]
    return chosen.stem, str(chosen.resolve())


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccipc search",
        description=get_description(_MANIFEST, fallback=_OWN_DESCRIPTION),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Output: JSONL on stdout, one record per hit.\n"
            "Pipe to: ccipc find-boundary | ccipc cassette | ccipc hydrate"
        ),
    )
    parser.add_argument(
        "--session", "-s", required=False,
        help=(
            "Session UUID (looked up under ~/.claude/projects/*/<uuid>.jsonl) "
            "OR direct path to a .jsonl file."
        ),
    )
    parser.add_argument(
        "--term", "-t", action="append", default=[],
        help="Search term (repeat for AND-search across all terms).",
    )
    parser.add_argument(
        "--type", dest="msg_type",
        choices=list(VALID_TRANSCRIPT_TYPES),
        help="Restrict matches to a single TranscriptMessage type.",
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=20,
        help="Maximum number of hits to emit (default: 20).",
    )
    parser.add_argument(
        "--context-chars", type=int, default=150,
        help="Characters of surrounding context per snippet (default: 150).",
    )
    parser.add_argument(
        "--all-sessions", action="store_true",
        help=(
            "[Phase 2] Search across all sessions. Not implemented in v0.1; "
            "raises an error if passed."
        ),
    )
    parser.add_argument(
        "--on-corrupt", choices=["skip", "raise"], default="skip",
        help="Behavior on malformed JSONL lines (default: skip).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point. Returns an exit code."""
    parser = _build_arg_parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv)

    try:
        # Phase 2 placeholder: --all-sessions is parsed but rejected.
        if args.all_sessions:
            raise errors.CLIUsageError(
                "--all-sessions is reserved for Phase 2 (multi-session search) and "
                "is not implemented in v0.1. Drop the flag and run within a single "
                "session for now."
            )

        # --session is technically optional in argparse to allow stdin-driven
        # candidate sessions in Phase 2, but in Phase 1 we require it.
        if not args.session:
            raise errors.CLIUsageError(
                "--session is required in Phase 1 (single-session search)."
            )
        if not args.term:
            raise errors.CLIUsageError(
                "at least one --term is required."
            )

        session_id, jsonl_path = _resolve_session_path(args.session)

        # Run the search.
        matches = jsonl_search.search_transcript(
            jsonl_path,
            args.term,
            context_chars=args.context_chars,
            type_filter=args.msg_type,
            on_corrupt=args.on_corrupt,
        )

        if not matches:
            raise errors.NoMatchesError(args.term, session_id=session_id)

        # Emit one JSONL record per hit, preserving line-order ranking.
        emitted = 0
        for m in matches:
            if emitted >= args.limit:
                break
            # Pick the FIRST snippet for the primary record; ranking by
            # line-order is sufficient for Phase 1.
            primary_snippet = m["snippets"][0] if m["snippets"] else {
                "snippet": "", "offset_start": None, "offset_end": None,
            }
            hit = schema.SearchHit(
                session_id=session_id,
                jsonl_path=jsonl_path,
                line_num=m["line_num"],
                uuid=m["uuid"],
                type=m["type"],
                snippet=primary_snippet["snippet"],
                score=1.0,  # line-order; Phase 2 may add term-density
                matched_terms=list(args.term),
                parent_uuid=m["parent_uuid"],
                is_sidechain=m["is_sidechain"],
                snippet_offset_start=primary_snippet["offset_start"],
                snippet_offset_end=primary_snippet["offset_end"],
            )
            schema.emit_record(hit.to_record())
            emitted += 1

        return errors.EXIT_OK

    except errors.CCIPCError as e:
        return errors.report_and_exit(e)
    except FileNotFoundError as e:
        # Map to a CCIPCError so error reporting is consistent.
        wrapped = errors.SessionNotFoundError(args.session or "(unknown)")
        return errors.report_and_exit(wrapped)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return errors.EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())

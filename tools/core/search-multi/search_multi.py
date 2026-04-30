"""ccipc search-multi -- Multi-JSONL full-text search across stored sessions.

v0 placeholder. Real Phase 1 implementation will:

1. Take session candidates from stdin (JSONL output of `csb search`) or via
   --session flags. Each candidate has a session_id and a jsonl_path.
2. Run substring AND-search across each candidate JSONL using the same
   recursive-string-extraction approach as scripts/search_sesslog.py, but
   parallelized across multiple files.
3. Emit ranked (session_id, msg_uuid, snippet, rank, type) records to stdout
   as JSONL, one per line, suitable for piping into ccipc find-boundary.

See: private/claude/ design plan, Section 5 (Phase 1 POC).
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv=None):
    """Entry point for search-multi (placeholder)."""
    parser = argparse.ArgumentParser(
        prog="ccipc search-multi",
        description="Multi-JSONL full-text search across Claude Code sessions.",
    )
    parser.add_argument(
        "--term", "-t", action="append", default=[],
        help="Search term (repeat for AND-search across all terms).",
    )
    parser.add_argument(
        "--session", "-s", action="append", default=[],
        help="Session ID or JSONL path (repeat for multi). "
             "If omitted, reads candidate sessions from stdin as JSONL.",
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=20,
        help="Maximum number of results to emit (default: 20).",
    )
    parser.add_argument(
        "--explain", action="store_true",
        help="Include match-confidence breakdown in output records.",
    )
    parser.add_argument(
        "--type", dest="msg_type",
        choices=["user", "assistant", "system", "attachment"],
        help="Restrict matches to a single TranscriptMessage type. "
             "tool_use/tool_result live inside assistant `message.content`, "
             "not at the top level (per Claude Code's logs.ts).",
    )

    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv)

    print(
        "ccipc search-multi: not yet implemented (v0 placeholder).",
        file=sys.stderr,
    )
    print(f"  terms:    {args.term or '(none)'}", file=sys.stderr)
    print(
        f"  sessions: {args.session or '(stdin or csb-search candidates)'}",
        file=sys.stderr,
    )
    print(f"  limit:    {args.limit}", file=sys.stderr)
    print(f"  type:     {args.msg_type or '(any)'}", file=sys.stderr)
    print(f"  explain:  {args.explain}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

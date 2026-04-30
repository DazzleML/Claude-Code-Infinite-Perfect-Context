"""ccipc find-boundary -- walk backward to the nearest user-turn boundary.

Reads SearchHit records on stdin, enriches each with boundary_* fields,
emits the enriched record on stdout. Records flat-merge (no field
stripping) so downstream cassette / cost-estimate / hydrate can chain.

Usage:

    ccipc search ... | ccipc find-boundary --before [--headroom-tokens N] [--include-pre-compact]

    # Or standalone:
    ccipc find-boundary --jsonl /path/to/session.jsonl --line 4231 [--headroom-tokens 25000]

The --headroom-tokens default is plan-aware (read from ~/.claude/ccipc/config.toml
or --plan flag). Larger plans get larger defaults because their 5h budget
can absorb more cassette tokens.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

# Bootstrap path to ccipc_lib (tools/core/<name>/script.py needs src/ on sys.path)
_HERE = Path(__file__).resolve().parent
for _ in range(5):
    candidate = _HERE / "src"
    if candidate.is_dir() and (candidate / "ccipc_lib").is_dir():
        sys.path.insert(0, str(candidate))
        break
    _HERE = _HERE.parent

from ccipc_lib import boundaries, errors, schema  # noqa: E402
from ccipc_lib.cc_constants import PLAN_DEFAULT_HEADROOM_TOKENS  # noqa: E402
from ccipc_lib.config import load_config  # noqa: E402
from ccipc_lib.tool_meta import get_description, load_tool_manifest  # noqa: E402

_MANIFEST = load_tool_manifest(__file__)
_OWN_DESCRIPTION = (
    "Walk backward from a search hit to the nearest user-turn boundary, "
    "applying plan-aware token-headroom."
)


def _resolve_headroom_tokens(
    explicit: Optional[int], plan_override: Optional[str]
) -> int:
    """Pick the effective --headroom-tokens value.

    Resolution order:
      1. --headroom-tokens explicit value
      2. plan-default from --plan flag
      3. plan-default from ~/.claude/ccipc/config.toml
      4. fallback: 30_000 (the API default)
    """
    if explicit is not None:
        return explicit
    if plan_override and plan_override in PLAN_DEFAULT_HEADROOM_TOKENS:
        return PLAN_DEFAULT_HEADROOM_TOKENS[plan_override]
    cfg = load_config()
    if cfg:
        # config-stored headroom OR plan-default
        if "default_headroom_tokens" in cfg:
            return int(cfg["default_headroom_tokens"])
        plan = cfg.get("plan")
        if plan in PLAN_DEFAULT_HEADROOM_TOKENS:
            return PLAN_DEFAULT_HEADROOM_TOKENS[plan]
    return PLAN_DEFAULT_HEADROOM_TOKENS["api"]


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ccipc find-boundary",
        description=get_description(_MANIFEST, fallback=_OWN_DESCRIPTION),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--before", action="store_true",
        help="Find the boundary BEFORE the hit (default mode for v0.1).",
    )
    p.add_argument(
        "--headroom-tokens", type=int, default=None,
        help=(
            "Token budget to reserve at the END of the cassette so the new "
            "session has room for new turns. Default is plan-aware."
        ),
    )
    p.add_argument(
        "--plan", choices=["max5", "max20", "api", "1m"], default=None,
        help=(
            "Override the plan for this invocation (affects default headroom). "
            "Without this, ~/.claude/ccipc/config.toml is consulted."
        ),
    )
    p.add_argument(
        "--include-pre-compact", action="store_true",
        help=(
            "Walk past SystemCompactBoundaryMessage lines. Default: hard stop "
            "at compact boundaries."
        ),
    )
    p.add_argument(
        "--jsonl", default=None,
        help=(
            "[standalone] Path to source JSONL when running without stdin. "
            "Required if no stdin is piped."
        ),
    )
    p.add_argument(
        "--line", type=int, default=None,
        help=(
            "[standalone] Target line number to walk back from. Required with --jsonl."
        ),
    )
    p.add_argument(
        "--on-corrupt", choices=["skip", "raise"], default="skip",
        help="Behavior on malformed JSONL lines (default: skip).",
    )
    return p


def _process_one(
    record: dict,
    *,
    headroom_tokens: int,
    include_pre_compact: bool,
    on_corrupt: str,
) -> Optional[dict]:
    """Find a boundary for one upstream record. Returns enriched dict or None.

    None signals "no usable boundary found" (the caller decides whether
    to skip or fail).
    """
    jsonl_path = record.get("jsonl_path")
    target_line = record.get("line_num")
    if not jsonl_path or not target_line:
        # Malformed record; skip rather than fail the whole batch.
        return None

    boundary = boundaries.find_boundary_before(
        jsonl_path,
        target_line,
        headroom_tokens=headroom_tokens,
        include_pre_compact=include_pre_compact,
        on_corrupt=on_corrupt,
    )
    if boundary is None:
        return None

    return schema.add_boundary_fields(
        record,
        boundary_line_num=boundary.line_num,
        boundary_uuid=boundary.uuid,
        boundary_type=boundary.boundary_type.value,
        turn_count=target_line - boundary.line_num,
        preceding_lines=boundary.preceding_lines,
        estimated_tokens_to_boundary=boundary.estimated_tokens_to_boundary,
        headroom_target_tokens=headroom_tokens,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv)

    try:
        headroom = _resolve_headroom_tokens(args.headroom_tokens, args.plan)

        # Two operation modes:
        #   - stdin mode: process JSONL records piped from `ccipc search`
        #   - standalone: --jsonl + --line provide a single virtual record
        if args.jsonl is not None or args.line is not None:
            if not (args.jsonl and args.line):
                raise errors.CLIUsageError(
                    "--jsonl and --line must be used together."
                )
            virtual = {
                "ccipc_schema_version": schema.CCIPC_SCHEMA_VERSION,
                "tool": "search",  # synthetic upstream marker
                "jsonl_path": str(Path(args.jsonl).resolve()),
                "line_num": args.line,
                "session_id": Path(args.jsonl).stem,
            }
            records = [virtual]
        else:
            if sys.stdin.isatty():
                raise errors.CLIUsageError(
                    "no records on stdin and no --jsonl provided. Pipe records "
                    "from `ccipc search` or pass --jsonl/--line."
                )
            records = schema.read_records(sys.stdin)
            if not records:
                raise errors.CLIUsageError(
                    "stdin closed without any records. Did the upstream tool error out?"
                )

        emitted = 0
        for rec in records:
            enriched = _process_one(
                rec,
                headroom_tokens=headroom,
                include_pre_compact=args.include_pre_compact,
                on_corrupt=args.on_corrupt,
            )
            if enriched is None:
                continue
            schema.emit_record(enriched)
            emitted += 1

        if emitted == 0:
            raise errors.NoMatchesError(
                terms=["(no usable boundaries)"],
                session_id=records[0].get("session_id") if records else None,
            )

        return errors.EXIT_OK

    except errors.CCIPCError as e:
        return errors.report_and_exit(e)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return errors.EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())

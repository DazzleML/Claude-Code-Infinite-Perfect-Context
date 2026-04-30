"""ccipc cost-estimate -- token + plan-aware cost preview for a cassette.

Reads a cassette record on stdin (with `cassette_path` field), or accepts
--cassette PATH for standalone use. Computes:

  - Token estimate via len(bytes) / 2 (matches CC's heuristic)
  - USD cost (model-aware; pricing as of cc_constants.PRICING_AS_OF)
  - Per-plan warnings: would_consume_pct, would_block (5h budget exceeded?)
  - Compaction warnings: how close to autocompact threshold / hard limit

Always exits 0. Warnings go to stderr. The structured warning data is
also added as fields on the JSONL stdout record so downstream `hydrate`
can enforce blocks (exit 5 unless --force-plan-overrun).

Plan-aware view first (per Round 4): "X% of your max5 5h budget" before
"$0.0Y.YY". For Max5 / Max20 users the API price is irrelevant; their
quota burn is the signal that matters.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
for _ in range(5):
    candidate = _HERE / "src"
    if candidate.is_dir() and (candidate / "ccipc_lib").is_dir():
        sys.path.insert(0, str(candidate))
        break
    _HERE = _HERE.parent

from ccipc_lib import cost, errors, schema  # noqa: E402
from ccipc_lib.config import get_or_prompt_config, load_config  # noqa: E402
from ccipc_lib.tool_meta import get_description, load_tool_manifest  # noqa: E402

_MANIFEST = load_tool_manifest(__file__)
_OWN_DESCRIPTION = (
    "Estimate token + USD cost of a cassette with plan-aware warnings."
)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ccipc cost-estimate",
        description=get_description(_MANIFEST, fallback=_OWN_DESCRIPTION),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--cassette", default=None,
        help="[standalone] Path to a cassette JSONL. Required when no stdin.",
    )
    p.add_argument(
        "--model", default=None,
        help=(
            "Model id for cost estimation (e.g. claude-sonnet-4-5). "
            "Falls back to ANTHROPIC_MODEL env, then to cc_constants.DEFAULT_MODEL."
        ),
    )
    p.add_argument(
        "--plan", choices=["max5", "max20", "api", "1m"], default=None,
        help=(
            "Override plan for this invocation. Without this, "
            "~/.claude/ccipc/config.toml is consulted."
        ),
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Suppress stderr human-readable warnings; emit only JSONL on stdout.",
    )
    return p


def _print_summary(estimate: cost.CostEstimate, plan: str) -> None:
    """Render a human-readable plan-first cost summary to stderr."""
    print("─── ccipc cost preview ───────────────────────────────────────────", file=sys.stderr)

    # Plan-first view.
    plan_warning = next((w for w in estimate.plan_warnings if w["plan"] == plan), None)
    if plan_warning is None:
        print(f"  Plan:       {plan} (no quota model)", file=sys.stderr)
    elif plan_warning.get("budget_tokens") is None:
        print(f"  Plan:       {plan} (no 5h cap)", file=sys.stderr)
    else:
        pct = plan_warning["would_consume_pct"]
        budget = plan_warning["budget_tokens"]
        block = " (EXCEEDS BUDGET)" if plan_warning["would_block"] else ""
        print(
            f"  Plan:       {plan} -- {pct:.1f}% of 5h budget "
            f"({estimate.estimated_tokens:,} / {budget:,} tokens){block}",
            file=sys.stderr,
        )

    # Raw API cost (secondary).
    print(
        f"  API cost:   ${estimate.estimated_cost_usd:.4f} "
        f"({estimate.estimated_tokens:,} input tokens @ "
        f"{estimate.model}, prices as of {estimate.pricing_as_of})",
        file=sys.stderr,
    )
    print(f"  Model:      {estimate.model} (source: {estimate.model_source})", file=sys.stderr)

    # Compaction warnings.
    if estimate.compaction_warnings:
        for w in estimate.compaction_warnings:
            sev = w.get("severity", "info").upper()
            msg = w.get("message", "")
            print(f"  [{sev}] {msg}", file=sys.stderr)

    # Other plan warnings (if user is curious about other plans).
    for pw in estimate.plan_warnings:
        if pw["plan"] == plan:
            continue
        if pw.get("budget_tokens") is None:
            continue
        block = " BLOCKED" if pw["would_block"] else ""
        print(
            f"    other plan {pw['plan']}: {pw['would_consume_pct']:.1f}% "
            f"({pw['budget_tokens']:,} budget){block}",
            file=sys.stderr,
        )

    print("──────────────────────────────────────────────────────────────────", file=sys.stderr)


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv)

    try:
        # Resolve input.
        if args.cassette:
            cassette_path = str(Path(args.cassette).resolve())
            record = {
                "ccipc_schema_version": schema.CCIPC_SCHEMA_VERSION,
                "cassette_path": cassette_path,
            }
        else:
            if sys.stdin.isatty():
                raise errors.CLIUsageError(
                    "no records on stdin and no --cassette provided. Pipe a "
                    "cassette record from `ccipc cassette` or pass --cassette."
                )
            records = schema.read_records(sys.stdin)
            if not records:
                raise errors.CLIUsageError(
                    "stdin closed without any records."
                )
            # Multiple records OK -- each gets its own estimate. Most
            # common case is exactly one cassette though.
            record = records[0] if len(records) == 1 else None
            if record is None:
                # Process all records sequentially.
                pass

            if record is None:
                # Plan-aware iteration.
                plan = (args.plan or (load_config() or {}).get("plan") or "api")
                for r in records:
                    cassette_path = r.get("cassette_path")
                    if not cassette_path:
                        continue
                    est = cost.estimate_cassette_cost(cassette_path, model=args.model)
                    if not args.quiet:
                        _print_summary(est, plan)
                    enriched = schema.add_cost_fields(
                        r,
                        estimated_tokens=est.estimated_tokens,
                        cost_usd=est.estimated_cost_usd,
                        model=est.model,
                        model_source=est.model_source,
                        pricing_basis=est.pricing_basis,
                        pricing_as_of=est.pricing_as_of,
                        plan_warnings=est.plan_warnings,
                        compaction_warnings=est.compaction_warnings,
                    )
                    schema.emit_record(enriched)
                return errors.EXIT_OK
            cassette_path = record.get("cassette_path")
            if not cassette_path:
                raise errors.CLIUsageError(
                    "input record is missing 'cassette_path' field; cannot estimate."
                )

        # Resolve plan: --plan flag, OR config, OR interactive prompt (TTY only).
        plan = args.plan
        if plan is None:
            cfg = get_or_prompt_config(plan_override=None)
            plan = cfg.get("plan", "api")

        est = cost.estimate_cassette_cost(cassette_path, model=args.model)

        if not args.quiet:
            _print_summary(est, plan)

        enriched = schema.add_cost_fields(
            record,
            estimated_tokens=est.estimated_tokens,
            cost_usd=est.estimated_cost_usd,
            model=est.model,
            model_source=est.model_source,
            pricing_basis=est.pricing_basis,
            pricing_as_of=est.pricing_as_of,
            plan_warnings=est.plan_warnings,
            compaction_warnings=est.compaction_warnings,
        )
        schema.emit_record(enriched)

        return errors.EXIT_OK

    except errors.CCIPCError as e:
        return errors.report_and_exit(e)
    except FileNotFoundError as e:
        wrapped = errors.CLIUsageError(f"cassette file not found: {e}")
        return errors.report_and_exit(wrapped)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return errors.EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())

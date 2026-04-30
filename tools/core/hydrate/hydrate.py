"""ccipc hydrate -- install a cassette and launch claude --resume.

Reads exactly ONE pipeline record on stdin (or accepts --cassette PATH
for standalone), enforces all the safety gates, atomically installs the
cassette under ~/.claude/projects/<slug>/<new-uuid>.jsonl, and runs
`claude --resume <new-uuid>`.

Safety gates (in order):
  1. Pipeline fan-in: stdin must have exactly 1 record (else exit 7)
  2. CC version compat: cassette major == current AND minor <= current
     (else exit 8 unless --force-cross-version-fork)
  3. Plan-overrun: if cost_plan_warnings show would_block=true, refuse
     (else exit 5 unless --force-plan-overrun)
  4. Cost-preview: interactive prompt unless --yes AND
     (CCIPC_ALLOW_AUTOHYDRATE=1 OR running with TTY)
  5. Target collision: if target jsonl already exists, exit 6
  6. Atomic install: write to .tmp, os.replace to final path

After install, `claude --resume <uuid>` is launched with stdio inherited.
On launch failure, emits HydrateLaunchError with manual-recovery hint.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
for _ in range(5):
    candidate = _HERE / "src"
    if candidate.is_dir() and (candidate / "ccipc_lib").is_dir():
        sys.path.insert(0, str(candidate))
        break
    _HERE = _HERE.parent

from ccipc_lib import cc_compat, cost, errors, schema, slug  # noqa: E402
from ccipc_lib._version import __version__ as CCIPC_VERSION  # noqa: E402
from ccipc_lib.cc_constants import CC_PROJECTS_SUBDIR  # noqa: E402
from ccipc_lib.config import load_config  # noqa: E402
from ccipc_lib.tool_meta import get_description, load_tool_manifest  # noqa: E402

_MANIFEST = load_tool_manifest(__file__)
_OWN_DESCRIPTION = (
    "Install a cassette and launch claude --resume to land in the forked session."
)


def _claude_home() -> Path:
    env = os.environ.get("CLAUDE_HOME")
    if env:
        return Path(env)
    return Path.home() / ".claude"


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ccipc hydrate",
        description=get_description(_MANIFEST, fallback=_OWN_DESCRIPTION),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--cassette", default=None,
        help="[standalone] Path to cassette JSONL. Required when no stdin.",
    )
    p.add_argument(
        "--cassette-cc-version", default=None,
        help=(
            "[standalone] CC version recorded in the cassette. Used by the "
            "compat check. Read from sidecar .json by default; pass this "
            "to override."
        ),
    )
    p.add_argument(
        "--yes", action="store_true",
        help=(
            "Skip the interactive cost-preview prompt. Requires "
            "CCIPC_ALLOW_AUTOHYDRATE=1 env var when stdin is not a TTY."
        ),
    )
    p.add_argument(
        "--force-plan-overrun", action="store_true",
        help=(
            "Bypass the plan-budget rejection (exit 5). Use only when you "
            "know you'll be rate-limited mid-session and accept that."
        ),
    )
    p.add_argument(
        "--force-cross-version-fork", action="store_true",
        help=(
            "Bypass the CC version compatibility check (exit 8). Use only "
            "when you've manually verified schema compatibility."
        ),
    )
    p.add_argument(
        "--no-claude-launch", action="store_true",
        help=(
            "Install the cassette and write sidecars but DO NOT launch "
            "`claude --resume`. Used by tests to exercise the install path "
            "without consuming tokens."
        ),
    )
    return p


def _enforce_fan_in(records: list[dict]) -> dict:
    """Stage 1 gate: pipeline fan-in must be exactly 1 record."""
    if not records:
        raise errors.CLIUsageError("no records on stdin and no --cassette provided.")
    return schema.reject_if_multiple(records, tool_name="hydrate")


def _enforce_version_compat(record: dict, args) -> None:
    """Stage 2 gate: cassette CC version must be compatible with current."""
    cassette_cc_version = (
        args.cassette_cc_version
        or record.get("cassette_cc_version_when_made")
        or record.get("cc_version_when_made")
        or ""
    )
    if not cassette_cc_version:
        # Legacy / unstamped cassette -- proceed silently. Phase 1.
        return
    cc_compat.assert_cassette_compatible(
        cassette_cc_version,
        cassette_path=record.get("cassette_path"),
        force=args.force_cross_version_fork,
    )


def _enforce_plan_budget(record: dict, args) -> None:
    """Stage 3 gate: cassette must fit the user's plan 5h budget."""
    plan_warnings = record.get("cost_plan_warnings", [])
    if not plan_warnings:
        return  # No cost-estimate run upstream; skip the check.
    cfg = load_config() or {}
    user_plan = cfg.get("plan", "api")
    relevant = next((w for w in plan_warnings if w["plan"] == user_plan), None)
    if relevant is None or not relevant.get("would_block"):
        return
    if args.force_plan_overrun:
        print(
            f"Warning: --force-plan-overrun: cassette exceeds {user_plan} 5h budget "
            f"({relevant['would_consume_pct']:.1f}%). Proceeding.",
            file=sys.stderr,
        )
        return
    raise errors.PlanBudgetExceededError(
        plan=user_plan,
        plan_budget=relevant.get("budget_tokens", 0),
        cassette_tokens=record.get("cost_estimated_tokens", 0),
    )


def _cost_preview_gate(record: dict, args) -> None:
    """Stage 4 gate: user-confirmation of the cost.

    Behavior matrix:

        --yes flag          stdin TTY?     CCIPC_ALLOW_AUTOHYDRATE?    Outcome
        ----------          ----------     -----------------------     -------
        no                  TTY            *                            interactive prompt
        no                  not TTY        *                            cost preview just printed; proceed (assumes upstream gate)
        yes                 TTY            *                            proceed (user typed --yes)
        yes                 not TTY        no                            REFUSE (env opt-in required for non-TTY agent runs)
        yes                 not TTY        yes                          proceed
    """
    is_tty = sys.stdin.isatty()
    auto_env = os.environ.get("CCIPC_ALLOW_AUTOHYDRATE") in ("1", "true", "yes")

    if args.yes:
        if not is_tty and not auto_env:
            raise errors.CLIUsageError(
                "--yes was passed in a non-TTY context without "
                "CCIPC_ALLOW_AUTOHYDRATE=1. Set the env var to authorize "
                "agent-driven hydrate, OR run interactively without --yes."
            )
        return  # authorized

    if not is_tty:
        # Non-interactive without --yes: surface the cost data and proceed.
        # Upstream cost-estimate already printed the human summary; the
        # caller is responsible for piping appropriately.
        return

    # Interactive prompt.
    tokens = record.get("cost_estimated_tokens", 0)
    usd = record.get("cost_usd", 0.0)
    plan_warnings = record.get("cost_plan_warnings", [])
    cfg = load_config() or {}
    user_plan = cfg.get("plan", "api")
    relevant = next((w for w in plan_warnings if w["plan"] == user_plan), None)
    plan_summary = ""
    if relevant and relevant.get("budget_tokens"):
        plan_summary = (
            f" ({relevant['would_consume_pct']:.1f}% of your {user_plan} 5h budget)"
        )

    print(
        f"\nccipc hydrate: about to install cassette\n"
        f"  Tokens:    {tokens:,}{plan_summary}\n"
        f"  API cost:  ${usd:.4f}\n"
        f"  Cassette:  {record.get('cassette_path', '<unknown>')}\n",
        file=sys.stderr,
    )
    while True:
        print("Proceed? [y/n]: ", end="", file=sys.stderr, flush=True)
        ans = sys.stdin.readline().strip().lower()
        if ans in ("y", "yes"):
            return
        if ans in ("n", "no", ""):
            raise errors.CostPreviewRejectedError(
                estimated_cost_usd=usd, estimated_tokens=tokens,
            )


def _atomic_install(src_cassette: Path, target: Path) -> None:
    """Copy cassette into place atomically.

    Writes to <target>.tmp first, then os.replace to <target>.
    Raises TargetCollisionError if <target> already exists.
    """
    if target.exists():
        raise errors.TargetCollisionError(str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f"_ccipc_hydrate_{target.name}.tmp"
    shutil.copyfile(src_cassette, tmp)
    os.replace(tmp, target)


def _launch_claude(new_uuid: str) -> int:
    """Run `claude --resume <new_uuid>`. Returns subprocess exit code."""
    if shutil.which("claude") is None:
        raise errors.HydrateLaunchError(
            cassette_path="(unknown)",
            new_uuid=new_uuid,
            subprocess_error="`claude` not on PATH",
        )
    try:
        result = subprocess.run(
            ["claude", "--resume", new_uuid],
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return result.returncode
    except OSError as e:
        raise errors.HydrateLaunchError(
            cassette_path="(installed)",
            new_uuid=new_uuid,
            subprocess_error=str(e),
        ) from e


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv)
    started = time.time()

    try:
        # Resolve input record.
        if args.cassette:
            cassette_path = str(Path(args.cassette).resolve())
            record = {
                "ccipc_schema_version": schema.CCIPC_SCHEMA_VERSION,
                "cassette_path": cassette_path,
                "cassette_new_uuid": "",  # auto-derived from filename below
            }
        else:
            if sys.stdin.isatty():
                raise errors.CLIUsageError(
                    "no records on stdin and no --cassette provided. Pipe a "
                    "cassette record from upstream tools or pass --cassette."
                )
            records = schema.read_records(sys.stdin)
            record = _enforce_fan_in(records)

        # Resolve cassette path and new uuid.
        cassette_path = Path(record.get("cassette_path", ""))
        if not cassette_path.is_file():
            raise errors.CLIUsageError(
                f"cassette file not found: {cassette_path}"
            )
        new_uuid = record.get("cassette_new_uuid") or cassette_path.stem

        # Apply gates in order.
        _enforce_version_compat(record, args)
        _enforce_plan_budget(record, args)
        _cost_preview_gate(record, args)

        # Determine target install path.
        # If the cassette was already written under ~/.claude/projects/<slug>/,
        # we treat it as already installed and skip the copy. Otherwise, we
        # install it under the cwd's slug.
        claude_home = _claude_home()
        projects_dir = claude_home / CC_PROJECTS_SUBDIR
        try:
            cassette_path.relative_to(projects_dir)
            already_installed = True
            target = cassette_path
        except ValueError:
            already_installed = False
            project_slug = slug.slug_from_cwd(os.getcwd())
            target = projects_dir / project_slug / f"{new_uuid}.jsonl"

        if not already_installed:
            _atomic_install(cassette_path, target)

        invocation = ["claude", "--resume", new_uuid]
        exit_code = errors.EXIT_OK

        if not args.no_claude_launch:
            exit_code = _launch_claude(new_uuid)

        duration = round(time.time() - started, 3)
        enriched = schema.add_hydrate_fields(
            record,
            installed_path=str(target),
            new_session_id=new_uuid,
            claude_invocation=invocation,
            exit_code=exit_code,
            duration_seconds=duration,
        )
        schema.emit_record(enriched)

        return exit_code

    except errors.CCIPCError as e:
        return errors.report_and_exit(e)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return errors.EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())

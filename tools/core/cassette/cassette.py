"""ccipc cassette --mode A -- build a verbatim JSONL prefix cassette.

Reads ONE BoundaryHit record on stdin (or via --boundary-* args), copies
the source JSONL verbatim up to and including the boundary line, writes
the cassette atomically (.tmp + os.replace), and emits a single cassette
record on stdout.

Atomic write: target written as <target>.tmp, then os.replace to <target>.
Conflict at target = exit 6 (TargetCollisionError).

Sidecar policy (per Round 4 design, verified empirically):
  <uuid>.json        : full state object with ccipc_* lineage fields
  <uuid>.name-cache  : "Fork of <orig-name>"
  <uuid>.source      : "ccipc-fork"
  (.run / .started   : NEVER -- those are CC's runtime markers)

Inline ccipc_meta:
  By default, the first user-message line of the cassette gets an
  injected `ccipc_meta` field (out-of-band schema stamping for
  self-describing cassettes). If CC's parser proves intolerant of unknown
  fields (test_jsonl_unknown_fields_compat.py), pass --no-inline-meta to
  fall back to sidecar-only stamping.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid as uuid_mod
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
for _ in range(5):
    candidate = _HERE / "src"
    if candidate.is_dir() and (candidate / "ccipc_lib").is_dir():
        sys.path.insert(0, str(candidate))
        break
    _HERE = _HERE.parent

from ccipc_lib import errors, schema, slug  # noqa: E402
from ccipc_lib._version import __version__ as CCIPC_VERSION  # noqa: E402
from ccipc_lib.cc_compat import get_installed_cc_version  # noqa: E402
from ccipc_lib.tool_meta import get_description, load_tool_manifest  # noqa: E402

_MANIFEST = load_tool_manifest(__file__)

# Short, tool-specified self-description. Used as a fallback when the
# manifest is unfindable AND available as a module-level constant for
# code that wants the tool's own concise summary independent of the
# (typically longer) manifest description shown by `ccipc info`.
_OWN_DESCRIPTION = "Build a Mode-A verbatim JSONL prefix cassette + sidecars."
from ccipc_lib.cc_constants import (  # noqa: E402
    CC_PROJECTS_SUBDIR,
    CC_SESSION_STATES_SUBDIR,
)


def _claude_home() -> Path:
    """Return ~/.claude/, override via CLAUDE_HOME env (used in tests)."""
    env = os.environ.get("CLAUDE_HOME")
    if env:
        return Path(env)
    return Path.home() / ".claude"


def _detect_orig_name(source_jsonl_path: str) -> str:
    """Best-effort recovery of the original session's display name.

    Strategy:
      1. Look for a sidecar <uuid>.name-cache and read it.
      2. Fall back to the basename of the cwd from the first JSONL line that has one.
      3. Fall back to "session".
    """
    p = Path(source_jsonl_path)
    sid = p.stem
    name_cache = _claude_home() / CC_SESSION_STATES_SUBDIR / f"{sid}.name-cache"
    if name_cache.exists():
        try:
            return name_cache.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cwd = obj.get("cwd") if isinstance(obj, dict) else None
                if cwd:
                    return Path(cwd).name
    except OSError:
        pass
    return "session"


def _build_cassette_jsonl(
    source_path: str,
    boundary_line_num: int,
    target_path: Path,
    *,
    new_uuid: str,
    source_session_id: str,
    boundary_uuid: str,
    cc_version: str,
    inline_meta: bool,
) -> tuple[str, int, int]:
    """Copy the source JSONL up to and including boundary_line_num.

    Writes to a temp file in the same directory as target_path (so the
    subsequent os.replace stays on a single filesystem -- on Windows,
    cross-volume replace raises OSError). Returns (tmp_path, lines_copied,
    byte_size). Caller is responsible for renaming to the final path
    atomically and for cleaning up the tmp on rename failure.

    If inline_meta is True, the FIRST encountered user-message line gets
    an injected ccipc_meta field (rewriting that one line). All other
    lines are byte-identical to source.
    """
    src = Path(source_path)
    if not src.is_file():
        raise errors.SessionNotFoundError(source_session_id, searched_paths=[str(src)])

    # Build the meta object once.
    meta_obj = {
        "ccipc_version": CCIPC_VERSION,
        "ccipc_schema_version": schema.CCIPC_SCHEMA_VERSION,
        "cc_version_when_made": cc_version,
        "ccipc_forked_from": source_session_id,
        "ccipc_boundary_uuid": boundary_uuid,
        "ccipc_mode": "A",
        "ccipc_created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    tmp_path = target_path.parent / f"_ccipc_cassette_{new_uuid}.tmp"
    lines_copied = 0
    byte_size = 0
    inline_injected = False

    try:
        with open(src, "r", encoding="utf-8") as fin, open(tmp_path, "w", encoding="utf-8", newline="\n") as fout:
            for line_num, line in enumerate(fin, 1):
                if line_num > boundary_line_num:
                    break

                # Possibly inject ccipc_meta into the first user-message line.
                if inline_meta and not inline_injected:
                    stripped = line.strip()
                    if stripped:
                        try:
                            obj = json.loads(stripped)
                        except json.JSONDecodeError:
                            obj = None
                        if isinstance(obj, dict) and obj.get("type") == "user":
                            obj["ccipc_meta"] = meta_obj
                            line = json.dumps(obj, ensure_ascii=False) + "\n"
                            inline_injected = True

                fout.write(line)
                lines_copied += 1
                byte_size += len(line.encode("utf-8"))
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    return str(tmp_path), lines_copied, byte_size


def _write_sidecars(
    *,
    new_uuid: str,
    cassette_path: Path,
    source_session_id: str,
    boundary_uuid: str,
    project_cwd: str,
    project_slug: str,
    cc_version: str,
    orig_name: str,
) -> dict[str, Path]:
    """Write the 3 required sidecar files. Returns dict of ext->path."""
    states_dir = _claude_home() / CC_SESSION_STATES_SUBDIR
    states_dir.mkdir(parents=True, exist_ok=True)

    json_path = states_dir / f"{new_uuid}.json"
    name_path = states_dir / f"{new_uuid}.name-cache"
    src_path = states_dir / f"{new_uuid}.source"

    state_obj = {
        "session_id": new_uuid,
        "transcript_path": str(cassette_path),
        "sessions_index_path": None,  # mirror CC's own behavior
        "sesslog_dir": None,
        "original_cwd": project_cwd,
        "cwd": project_cwd,
        "current_name": f"Fork of {orig_name}",
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        # ccipc lineage extension fields:
        "ccipc_version": CCIPC_VERSION,
        "ccipc_schema_version": schema.CCIPC_SCHEMA_VERSION,
        "ccipc_forked_from": source_session_id,
        "ccipc_boundary_uuid": boundary_uuid,
        "ccipc_mode": "A",
        "ccipc_created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ccipc_project_slug": project_slug,
        "cc_version_when_made": cc_version,
    }
    json_path.write_text(json.dumps(state_obj, indent=2), encoding="utf-8")
    name_path.write_text(f"Fork of {orig_name}", encoding="utf-8")
    src_path.write_text("ccipc-fork", encoding="utf-8")
    return {".json": json_path, ".name-cache": name_path, ".source": src_path}


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ccipc cassette",
        description=get_description(_MANIFEST, fallback=_OWN_DESCRIPTION),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--mode", choices=["A"], default="A",
        help="Cassette mode. Only 'A' (verbatim past) supported in v0.1.",
    )
    p.add_argument(
        "--output", "-o", default=None,
        help=(
            "Cassette output path. Default: derived from cwd's slug at "
            "~/.claude/projects/<slug>/<new-uuid>.jsonl"
        ),
    )
    p.add_argument(
        "--no-inline-meta", action="store_true",
        help=(
            "Skip injecting the inline ccipc_meta field on the first "
            "user-message line. Use this if CC's parser proves intolerant "
            "of unknown JSONL fields. Sidecar stamping still happens."
        ),
    )
    # Standalone-mode args (when stdin is empty):
    p.add_argument(
        "--jsonl", default=None,
        help="[standalone] Source JSONL path. Required when no stdin.",
    )
    p.add_argument(
        "--boundary-line", type=int, default=None,
        help="[standalone] Boundary line number in the source JSONL.",
    )
    p.add_argument(
        "--boundary-uuid", default=None,
        help="[standalone] Boundary UUID for lineage tracking.",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv)

    try:
        # Resolve input record either from stdin or standalone flags.
        if args.jsonl or args.boundary_line:
            if not (args.jsonl and args.boundary_line):
                raise errors.CLIUsageError(
                    "--jsonl and --boundary-line must be used together."
                )
            jsonl_path = str(Path(args.jsonl).resolve())
            record = {
                "ccipc_schema_version": schema.CCIPC_SCHEMA_VERSION,
                "jsonl_path": jsonl_path,
                "session_id": Path(jsonl_path).stem,
                "boundary_line_num": args.boundary_line,
                "boundary_uuid": args.boundary_uuid or "",
            }
        else:
            if sys.stdin.isatty():
                raise errors.CLIUsageError(
                    "no records on stdin and no --jsonl provided. Pipe a "
                    "BoundaryHit from `ccipc find-boundary` or pass "
                    "--jsonl + --boundary-line."
                )
            records = schema.read_records(sys.stdin)
            record = schema.reject_if_multiple(records, tool_name="cassette")

        # Validate required fields on the boundary record.
        for required in ("jsonl_path", "boundary_line_num", "session_id"):
            if not record.get(required):
                raise errors.CLIUsageError(
                    f"input record is missing required field: {required!r}"
                )

        source_jsonl = record["jsonl_path"]
        boundary_line = int(record["boundary_line_num"])
        source_session_id = record["session_id"]
        boundary_uuid = record.get("boundary_uuid", "")

        # Generate a new uuid for the cassette session.
        new_uuid = str(uuid_mod.uuid4())

        # Resolve target output path.
        if args.output:
            target = Path(args.output).resolve()
        else:
            cwd = os.getcwd()
            project_slug = slug.slug_from_cwd(cwd)
            target = _claude_home() / CC_PROJECTS_SUBDIR / project_slug / f"{new_uuid}.jsonl"

        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            raise errors.TargetCollisionError(str(target))

        # Detect CC version (best-effort; missing CC just records empty).
        cc_ver = get_installed_cc_version()
        cc_version_str = str(cc_ver) if cc_ver else "unknown"

        orig_name = _detect_orig_name(source_jsonl)

        # Build the cassette to a temp file next to the final target
        # (must be on the same filesystem for os.replace to succeed on
        # Windows).
        tmp_path, lines_copied, byte_size = _build_cassette_jsonl(
            source_jsonl,
            boundary_line,
            target,
            new_uuid=new_uuid,
            source_session_id=source_session_id,
            boundary_uuid=boundary_uuid,
            cc_version=cc_version_str,
            inline_meta=not args.no_inline_meta,
        )
        # Atomic rename to final path.
        try:
            os.replace(tmp_path, target)
        except OSError:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
            raise

        # Estimated tokens via the bytes/2 heuristic.
        estimated_tokens = byte_size // 2

        # Write the 3 sidecars.
        cwd = os.getcwd()
        project_slug = slug.slug_from_cwd(cwd)
        _write_sidecars(
            new_uuid=new_uuid,
            cassette_path=target,
            source_session_id=source_session_id,
            boundary_uuid=boundary_uuid,
            project_cwd=cwd,
            project_slug=project_slug,
            cc_version=cc_version_str,
            orig_name=orig_name,
        )

        # Emit the enriched record.
        enriched = schema.add_cassette_fields(
            record,
            cassette_path=str(target),
            new_uuid=new_uuid,
            source_session_id=source_session_id,
            boundary_uuid=boundary_uuid,
            lines_copied=lines_copied,
            byte_size=byte_size,
            estimated_tokens=estimated_tokens,
            mode="A",
            cc_version_when_made=cc_version_str,
            ccipc_version=CCIPC_VERSION,
        )
        schema.emit_record(enriched)

        return errors.EXIT_OK

    except errors.CCIPCError as e:
        return errors.report_and_exit(e)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return errors.EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())

"""Pipeline smoke test -- exercise search → find-boundary → cassette → cost-estimate.

NOT a unit test. This is a hand-runnable validation script that drives
the four pipeline tools against the synthetic fixture and prints what
each stage produces. Hydrate is exercised with --no-claude-launch to
avoid burning real `claude --resume` tokens.

Usage:
    python tests/one-offs/smoke_pipeline.py

Prints PASS/FAIL summary at the end.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "synthetic_session.jsonl"
SRC_DIR = REPO_ROOT / "src"

TOOLS = {
    "search": REPO_ROOT / "tools" / "core" / "search" / "search.py",
    "find-boundary": REPO_ROOT / "tools" / "core" / "find-boundary" / "find_boundary.py",
    "cassette": REPO_ROOT / "tools" / "core" / "cassette" / "cassette.py",
    "cost-estimate": REPO_ROOT / "tools" / "core" / "cost-estimate" / "cost_estimate.py",
    "hydrate": REPO_ROOT / "tools" / "core" / "hydrate" / "hydrate.py",
}


def run(cmd, *, stdin_data: str | None = None, env_extra: dict | None = None):
    """Run a subprocess. Returns (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    # Make sure the lib path is reachable.
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        cmd,
        input=stdin_data,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def banner(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main():
    if not FIXTURE.is_file():
        print(f"FAIL: fixture not found at {FIXTURE}")
        return 1

    results = {}
    workspace = Path(tempfile.mkdtemp(prefix="ccipc_smoke_"))
    fake_claude_home = workspace / "fake_claude_home"
    (fake_claude_home / "projects").mkdir(parents=True)
    (fake_claude_home / "session-states").mkdir(parents=True)
    fake_ccipc_config = fake_claude_home / "ccipc"
    fake_ccipc_config.mkdir(parents=True)
    (fake_ccipc_config / "config.toml").write_text(
        'config_version = 1\nplan = "api"\ndefault_headroom_tokens = 100\n',
        encoding="utf-8",
    )

    env_extra = {
        "CLAUDE_HOME": str(fake_claude_home),
        "CCIPC_CONFIG_DIR": str(fake_ccipc_config),
    }

    try:
        # ── Stage 1: search ────────────────────────────────────────────────
        banner("STAGE 1: search --term NEEDLE-ALPHA --type user")
        rc, out, err = run(
            [sys.executable, str(TOOLS["search"]), "--session", str(FIXTURE),
             "--term", "NEEDLE-ALPHA", "--type", "user"],
            env_extra=env_extra,
        )
        print(f"  exit={rc}")
        print(f"  stdout: {out.rstrip()}")
        if err.strip():
            print(f"  stderr: {err.rstrip()}")
        results["search"] = (rc == 0 and "NEEDLE-ALPHA" in out)
        search_output = out

        # ── Stage 2: find-boundary ────────────────────────────────────────
        banner("STAGE 2: find-boundary --before --headroom-tokens 100 (piped)")
        rc, out, err = run(
            [sys.executable, str(TOOLS["find-boundary"]), "--before",
             "--headroom-tokens", "100", "--plan", "api"],
            stdin_data=search_output,
            env_extra=env_extra,
        )
        print(f"  exit={rc}")
        print(f"  stdout: {out.rstrip()}")
        if err.strip():
            print(f"  stderr: {err.rstrip()}")
        results["find-boundary"] = (rc == 0 and "boundary_uuid" in out)
        boundary_output = out

        # ── Stage 3: cassette ────────────────────────────────────────────
        banner("STAGE 3: cassette --mode A --output <tmp> (piped)")
        cassette_target = workspace / "test_cassette.jsonl"
        # cassette derives target from cwd's slug by default. Force --output here.
        rc, out, err = run(
            [sys.executable, str(TOOLS["cassette"]), "--mode", "A",
             "--output", str(cassette_target), "--no-inline-meta"],
            stdin_data=boundary_output,
            env_extra=env_extra,
        )
        print(f"  exit={rc}")
        print(f"  stdout: {out.rstrip()}")
        if err.strip():
            print(f"  stderr: {err.rstrip()}")
        results["cassette"] = (
            rc == 0
            and cassette_target.is_file()
            and cassette_target.stat().st_size > 0
        )
        cassette_output = out

        # ── Stage 4: cost-estimate ────────────────────────────────────────
        banner("STAGE 4: cost-estimate --plan max5 (piped)")
        rc, out, err = run(
            [sys.executable, str(TOOLS["cost-estimate"]), "--plan", "max5"],
            stdin_data=cassette_output,
            env_extra=env_extra,
        )
        print(f"  exit={rc}")
        print(f"  stdout: {out.rstrip()[:400]}")
        if err.strip():
            print(f"  stderr (cost preview):\n{err.rstrip()}")
        results["cost-estimate"] = (rc == 0 and "cost_usd" in out)
        cost_output = out

        # ── Stage 5: hydrate --no-claude-launch (piped) ───────────────────
        banner("STAGE 5: hydrate --no-claude-launch --yes (piped)")
        rc, out, err = run(
            [sys.executable, str(TOOLS["hydrate"]),
             "--no-claude-launch", "--yes"],
            stdin_data=cost_output,
            env_extra={**env_extra, "CCIPC_ALLOW_AUTOHYDRATE": "1"},
        )
        print(f"  exit={rc}")
        print(f"  stdout: {out.rstrip()[:400]}")
        if err.strip():
            print(f"  stderr: {err.rstrip()}")
        results["hydrate"] = (rc == 0 and "hydrate_installed_path" in out)

        # ── Pipeline fan-in rejection sanity check ───────────────────────
        banner("EXTRA: cassette refuses 2 stdin records (exit 7)")
        # Construct a 2-record stream by duplicating the boundary output.
        two_records = boundary_output + boundary_output
        rc, out, err = run(
            [sys.executable, str(TOOLS["cassette"]), "--mode", "A",
             "--output", str(workspace / "should_fail.jsonl"),
             "--no-inline-meta"],
            stdin_data=two_records,
            env_extra=env_extra,
        )
        print(f"  exit={rc} (expect 7)")
        if err.strip():
            print(f"  stderr: {err.rstrip()[:200]}")
        results["fan-in-rejection"] = (rc == 7)

    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    # ── Summary ───────────────────────────────────────────────────────
    banner("SUMMARY")
    all_pass = True
    for stage, passed in results.items():
        marker = "[OK]  " if passed else "[FAIL]"
        print(f"  {marker} {stage}")
        all_pass = all_pass and passed
    print()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

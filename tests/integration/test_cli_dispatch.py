"""Integration tests for the `ccipc` CLI dispatcher (dazzlecmd-lib AggregatorEngine).

These exercise the *actual* `python -m ccipc <subcommand>` pathway --
the same one a user runs via the `ccipc` script after `pip install`.
This catches regressions in:

  - Tool manifest discovery (`tools/core/*/.ccipc.json`)
  - Kit filtering (`kits/core.kit.json`)
  - Argument forwarding through AggregatorEngine
  - Help-text composition (epilog_builder)
  - The `_find_ccipc_project_root()` walker

Without these, our unit tests would happily pass even if the dispatcher
broke.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
SRC = _REPO / "src"
FIXTURE = _REPO / "tests" / "fixtures" / "synthetic_session.jsonl"


def _run_ccipc(args, *, stdin_data: str = "", env_extra: dict | None = None):
    """Invoke `python -m ccipc <args>` with PYTHONPATH set."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, "-m", "ccipc"] + list(args)
    proc = subprocess.run(
        cmd, input=stdin_data, capture_output=True, text=True, env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


@pytest.fixture
def isolated_claude_home(tmp_path):
    """Create a fake CLAUDE_HOME with a config so prompts don't block."""
    home = tmp_path / "fake_claude_home"
    (home / "projects").mkdir(parents=True)
    (home / "session-states").mkdir(parents=True)
    cfg_dir = home / "ccipc"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.toml").write_text(
        'config_version = 1\nplan = "api"\ndefault_headroom_tokens = 100\n',
        encoding="utf-8",
    )
    return {
        "CLAUDE_HOME": str(home),
        "CCIPC_CONFIG_DIR": str(cfg_dir),
    }


# ─── Meta commands (dazzlecmd-lib) ──────────────────────────────────────

class TestMetaCommands:
    def test_help(self):
        rc, out, err = _run_ccipc(["--help"])
        assert rc == 0
        assert "ccipc" in out
        assert "core tools:" in out
        # All 5 tools should be discovered.
        for name in ("search", "find-boundary", "cassette", "cost-estimate", "hydrate"):
            assert name in out, f"tool {name} missing from help"

    def test_version(self):
        rc, out, err = _run_ccipc(["--version"])
        assert rc == 0
        # Version follows PEP 440 with optional dev tag.
        assert "ccipc" in out.lower() or "0." in out

    def test_list_meta_command(self):
        rc, out, err = _run_ccipc(["list"])
        # `list` is a dazzlecmd-lib meta-command. May exit 0 with tool list.
        assert rc == 0
        assert "search" in out
        assert "cassette" in out


# ─── Tool dispatch (search) ──────────────────────────────────────────────

class TestSearchDispatch:
    def test_search_help_via_dispatcher(self):
        rc, out, err = _run_ccipc(["search", "--help"])
        assert rc == 0
        assert "--term" in out
        assert "--session" in out
        assert "--type" in out

    def test_search_finds_needle_via_dispatcher(self):
        rc, out, err = _run_ccipc([
            "search", "--session", str(FIXTURE),
            "--term", "NEEDLE-ALPHA", "--type", "user",
        ])
        assert rc == 0, f"search failed: {err}"
        # Output is JSONL on stdout.
        line = out.strip().splitlines()[0]
        rec = json.loads(line)
        assert rec["tool"] == "search"
        assert rec["uuid"] == "u-003"
        assert rec["matched_terms"] == ["NEEDLE-ALPHA"]

    def test_search_no_matches_exits_2(self):
        rc, out, err = _run_ccipc([
            "search", "--session", str(FIXTURE),
            "--term", "NONEXISTENT-TERM-XYZ",
        ])
        assert rc == 2, f"expected exit 2, got {rc}"
        assert "no matches" in err.lower()

    def test_search_invalid_session_path(self):
        rc, out, err = _run_ccipc([
            "search", "--session", "/nonexistent/path.jsonl",
            "--term", "x",
        ])
        assert rc != 0
        assert "could not find" in err.lower() or "not found" in err.lower()

    def test_search_all_sessions_rejected_in_phase_1(self):
        rc, out, err = _run_ccipc([
            "search", "--session", str(FIXTURE),
            "--term", "x", "--all-sessions",
        ])
        # --all-sessions is parsed but rejected (Phase 2 placeholder).
        assert rc != 0
        assert "phase 2" in err.lower() or "not implemented" in err.lower()


# ─── Tool dispatch (find-boundary) ──────────────────────────────────────

class TestFindBoundaryDispatch:
    def test_find_boundary_help(self):
        rc, out, err = _run_ccipc(["find-boundary", "--help"])
        assert rc == 0
        assert "--headroom-tokens" in out
        assert "--include-pre-compact" in out

    def test_find_boundary_standalone(self, isolated_claude_home):
        rc, out, err = _run_ccipc(
            ["find-boundary", "--before",
             "--jsonl", str(FIXTURE),
             "--line", "5",
             "--headroom-tokens", "0",
             "--plan", "api"],
            env_extra=isolated_claude_home,
        )
        assert rc == 0, f"find-boundary failed: {err}"
        rec = json.loads(out.strip().splitlines()[0])
        assert rec["tool"] == "find-boundary"
        assert rec["boundary_uuid"] == "u-003"


# ─── Full pipeline via dispatcher ───────────────────────────────────────

class TestFullPipelineViaDispatcher:
    def test_search_into_find_boundary(self, isolated_claude_home):
        # Stage 1: search via dispatcher.
        rc1, search_out, err1 = _run_ccipc([
            "search", "--session", str(FIXTURE),
            "--term", "NEEDLE-ALPHA", "--type", "user",
        ])
        assert rc1 == 0, f"search failed: {err1}"

        # Stage 2: find-boundary via dispatcher, piped from search output.
        rc2, fb_out, err2 = _run_ccipc(
            ["find-boundary", "--before",
             "--headroom-tokens", "100",
             "--plan", "api"],
            stdin_data=search_out,
            env_extra=isolated_claude_home,
        )
        assert rc2 == 0, f"find-boundary failed: {err2}"
        rec = json.loads(fb_out.strip().splitlines()[0])
        # Flat-merge invariant: upstream search fields preserved.
        assert rec["matched_terms"] == ["NEEDLE-ALPHA"]
        # find-boundary added its own fields.
        assert rec["boundary_uuid"] == "u-003"
        assert rec["boundary_type"] == "user_turn"

    def test_full_4_stage_pipeline_via_dispatcher(
        self, tmp_path, isolated_claude_home,
    ):
        # search → find-boundary → cassette → cost-estimate (no hydrate to
        # avoid burning real claude tokens).
        cassette_target = tmp_path / "test_cassette.jsonl"

        rc, search_out, err = _run_ccipc(
            ["search", "--session", str(FIXTURE),
             "--term", "NEEDLE-ALPHA", "--type", "user"],
        )
        assert rc == 0, err

        rc, fb_out, err = _run_ccipc(
            ["find-boundary", "--before", "--headroom-tokens", "100",
             "--plan", "api"],
            stdin_data=search_out,
            env_extra=isolated_claude_home,
        )
        assert rc == 0, err

        rc, cas_out, err = _run_ccipc(
            ["cassette", "--mode", "A",
             "--output", str(cassette_target),
             "--no-inline-meta"],
            stdin_data=fb_out,
            env_extra=isolated_claude_home,
        )
        assert rc == 0, err
        assert cassette_target.is_file()
        assert cassette_target.stat().st_size > 0

        rc, cost_out, err = _run_ccipc(
            ["cost-estimate", "--plan", "max5", "--quiet"],
            stdin_data=cas_out,
            env_extra=isolated_claude_home,
        )
        assert rc == 0, err
        rec = json.loads(cost_out.strip().splitlines()[0])
        # Verify the entire field chain through the pipeline.
        assert rec["matched_terms"] == ["NEEDLE-ALPHA"]      # from search
        assert rec["boundary_uuid"] == "u-003"               # from find-boundary
        assert rec["cassette_lines_copied"] == 5             # from cassette
        assert rec["cost_model"] == "claude-sonnet-4-5"      # from cost-estimate
        # Plan warnings should include all 4 plans.
        plan_warnings = rec["cost_plan_warnings"]
        plans = {w["plan"] for w in plan_warnings}
        assert plans == {"max5", "max20", "api", "1m"}


# ─── Bad usage / error paths via dispatcher ─────────────────────────────

class TestErrorPathsViaDispatcher:
    def test_unknown_subcommand(self):
        rc, out, err = _run_ccipc(["nonexistent-tool"])
        assert rc != 0
        # dazzlecmd-lib should produce an error mentioning the tool.
        combined = (out + err).lower()
        assert "nonexistent-tool" in combined or "unknown" in combined or "not found" in combined

    def test_search_missing_required_arg(self):
        # No --term given -- argparse should error.
        rc, out, err = _run_ccipc(["search", "--session", str(FIXTURE)])
        # search.py raises CLIUsageError when --term is empty.
        assert rc != 0

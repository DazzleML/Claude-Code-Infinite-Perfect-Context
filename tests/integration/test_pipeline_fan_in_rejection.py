"""Integration test: cassette and hydrate refuse stdin with > 1 record (exit 7).

Per Round 2 design (Gemini's catch): single-target tools must NOT silently
pick the first record and discard the rest. They must emit a clear error
and exit 7.
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
CASSETTE_TOOL = _REPO / "tools" / "core" / "cassette" / "cassette.py"
HYDRATE_TOOL = _REPO / "tools" / "core" / "hydrate" / "hydrate.py"
FIXTURE = _REPO / "tests" / "fixtures" / "synthetic_session.jsonl"


def _run(cmd, *, stdin_data: str = "", env_extra: dict | None = None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        cmd, input=stdin_data, capture_output=True, text=True, env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _make_boundary_record(tmp_path: Path) -> dict:
    """Construct a minimal valid BoundaryHit record."""
    return {
        "ccipc_schema_version": "0.1",
        "tool": "find-boundary",
        "session_id": "synthetic_session",
        "jsonl_path": str(FIXTURE),
        "line_num": 5,
        "uuid": "u-003",
        "type": "user",
        "boundary_line_num": 5,
        "boundary_uuid": "u-003",
        "boundary_type": "user_turn",
        "turn_count": 0,
        "preceding_lines": 4,
        "estimated_tokens_to_boundary": 341,
        "headroom_target_tokens": 100,
    }


def test_cassette_rejects_two_records(tmp_path):
    rec = _make_boundary_record(tmp_path)
    stdin_data = json.dumps(rec) + "\n" + json.dumps(rec) + "\n"
    rc, _, err = _run(
        [sys.executable, str(CASSETTE_TOOL),
         "--mode", "A", "--output", str(tmp_path / "cassette.jsonl"),
         "--no-inline-meta"],
        stdin_data=stdin_data,
    )
    assert rc == 7, f"expected exit 7, got {rc}; stderr={err}"
    assert "stdin has 2 records" in err
    assert "head -n 1" in err  # recovery hint must be present


def test_cassette_accepts_one_record(tmp_path):
    rec = _make_boundary_record(tmp_path)
    fake_home = tmp_path / "fake_claude_home"
    (fake_home / "session-states").mkdir(parents=True)
    rc, _, err = _run(
        [sys.executable, str(CASSETTE_TOOL),
         "--mode", "A", "--output", str(tmp_path / "cassette.jsonl"),
         "--no-inline-meta"],
        stdin_data=json.dumps(rec) + "\n",
        env_extra={"CLAUDE_HOME": str(fake_home)},
    )
    assert rc == 0, f"expected success, got {rc}; stderr={err}"
    assert (tmp_path / "cassette.jsonl").is_file()


def test_hydrate_rejects_two_records(tmp_path):
    # Construct a cassette-style record (would be downstream of cassette tool).
    cassette_path = tmp_path / "fake_cassette.jsonl"
    cassette_path.write_text("{}\n", encoding="utf-8")
    rec = {
        "ccipc_schema_version": "0.1",
        "tool": "cassette",
        "cassette_path": str(cassette_path),
        "cassette_new_uuid": "fake-uuid",
    }
    stdin_data = json.dumps(rec) + "\n" + json.dumps(rec) + "\n"
    rc, _, err = _run(
        [sys.executable, str(HYDRATE_TOOL),
         "--no-claude-launch", "--yes"],
        stdin_data=stdin_data,
        env_extra={"CCIPC_ALLOW_AUTOHYDRATE": "1"},
    )
    assert rc == 7, f"expected exit 7, got {rc}; stderr={err}"
    assert "stdin has 2 records" in err


def test_cassette_rejects_zero_records(tmp_path):
    # Empty stdin -> error with helpful message.
    rc, _, err = _run(
        [sys.executable, str(CASSETTE_TOOL),
         "--mode", "A", "--output", str(tmp_path / "cassette.jsonl"),
         "--no-inline-meta"],
        stdin_data="",  # empty stdin
    )
    # Note: empty stdin in subprocess mode is non-TTY but no records.
    # Tool should error, not hang.
    assert rc != 0, f"expected non-zero exit, got {rc}; stderr={err}"

"""Unit tests for ccipc_lib.boundaries against the synthetic fixture."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from ccipc_lib.boundaries import (  # noqa: E402
    BoundaryType,
    count_compact_boundaries,
    find_boundary_before,
)

FIXTURE = _REPO / "tests" / "fixtures" / "synthetic_session.jsonl"


def test_fixture_exists():
    assert FIXTURE.is_file(), f"missing fixture: {FIXTURE}"


def test_count_compact_boundaries():
    # The fixture has exactly 1 SystemCompactBoundaryMessage at line 9.
    assert count_compact_boundaries(FIXTURE) == 1


def test_walk_back_to_user_turn_basic():
    # Target line 6 (assistant turn). Walk back should land on line 5 (user-turn).
    b = find_boundary_before(FIXTURE, target_line_num=6, headroom_tokens=0)
    assert b is not None
    assert b.boundary_type == BoundaryType.USER_TURN
    assert b.line_num == 5
    assert b.uuid == "u-003"


def test_skip_sidechain_turns():
    # Lines 7 and 8 are sidechain user/assistant. Walking back from line 9
    # (compact boundary) without crossing it should land on line 5.
    b = find_boundary_before(FIXTURE, target_line_num=9, headroom_tokens=0)
    assert b is not None
    # The boundary line 9 IS the compact line itself when we hit it walking back.
    assert b.boundary_type == BoundaryType.COMPACT_HARD_STOP
    assert b.uuid == "compact-001"


def test_walk_back_finds_post_compact_user_turn():
    # Walk back from line 11 (post-compact assistant). The closest user-turn
    # walking back is line 10 (post-compact user u-004). Even though there
    # IS a compact boundary at line 9, the walk stops at line 10 because
    # a user-turn was found before reaching the compact line.
    b = find_boundary_before(FIXTURE, target_line_num=11, headroom_tokens=0)
    assert b is not None
    assert b.boundary_type == BoundaryType.USER_TURN
    assert b.line_num == 10
    assert b.uuid == "u-004"


def test_compact_hard_stop_when_user_turn_rejected_by_headroom():
    # If headroom_tokens is large enough that the post-compact user-turn
    # at line 10 is rejected, the walk continues backward past it and
    # hits the compact boundary at line 9 (hard stop).
    # Total fixture is small (~1.7K bytes ≈ 850 tokens). Setting headroom=900
    # makes max_acceptable < 0, so all user-turns get rejected.
    b = find_boundary_before(
        FIXTURE,
        target_line_num=11,
        headroom_tokens=10_000,  # bigger than total fixture tokens
    )
    assert b is not None
    assert b.boundary_type == BoundaryType.COMPACT_HARD_STOP
    assert b.line_num == 9
    assert b.uuid == "compact-001"


def test_include_pre_compact_walks_through():
    # With --include-pre-compact, walking back from line 11 should reach
    # the user-turn at line 10 (post-compact user turn) -- it's the
    # FIRST user turn we hit walking back.
    b = find_boundary_before(
        FIXTURE,
        target_line_num=11,
        headroom_tokens=0,
        include_pre_compact=True,
    )
    assert b is not None
    assert b.boundary_type == BoundaryType.USER_TURN
    assert b.line_num == 10
    assert b.uuid == "u-004"


def test_target_line_at_user_turn_returns_self():
    # If target IS already a user-turn, the boundary is the target itself.
    b = find_boundary_before(FIXTURE, target_line_num=5, headroom_tokens=0)
    assert b is not None
    assert b.boundary_type == BoundaryType.USER_TURN
    assert b.line_num == 5


def test_session_start_fallback_when_no_user_turn_exists(tmp_path):
    # Build a tiny fixture with NO user turns, just a system message.
    p = tmp_path / "no_user.jsonl"
    p.write_text(
        '{"type":"system","uuid":"s1","parentUuid":null,"isSidechain":false,"message":{"role":"system","content":"only sys"}}\n'
        '{"type":"assistant","uuid":"a1","parentUuid":"s1","isSidechain":false,"message":{"role":"assistant","content":[{"type":"text","text":"hi"}]}}\n',
        encoding="utf-8",
    )
    b = find_boundary_before(p, target_line_num=2, headroom_tokens=0)
    assert b is not None
    assert b.boundary_type == BoundaryType.SESSION_START
    assert b.line_num == 1

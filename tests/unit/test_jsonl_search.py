"""Unit tests for ccipc_lib.jsonl_search against the synthetic fixture."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from ccipc_lib.jsonl_search import (  # noqa: E402
    extract_strings,
    find_context,
    search_transcript,
)
from ccipc_lib.errors import CorruptJSONLError  # noqa: E402

FIXTURE = _REPO / "tests" / "fixtures" / "synthetic_session.jsonl"


class TestExtractStrings:
    def test_flat_dict(self):
        out = list(extract_strings({"a": "x", "b": "y"}))
        assert sorted(out) == ["x", "y"]

    def test_nested_dict(self):
        out = list(extract_strings({"a": {"b": {"c": "deep"}}}))
        assert out == ["deep"]

    def test_list_of_strings(self):
        out = list(extract_strings(["x", "y", "z"]))
        assert out == ["x", "y", "z"]

    def test_max_depth(self):
        # 8 levels deep, max_depth=6 => stops before reaching the inner string.
        nested = "deep"
        for _ in range(8):
            nested = {"k": nested}
        out = list(extract_strings(nested, max_depth=6))
        assert out == []  # truncated before reaching the leaf

    def test_non_string_non_container_skipped(self):
        out = list(extract_strings({"a": 1, "b": 2.5, "c": None, "d": "yes"}))
        assert out == ["yes"]


class TestFindContext:
    def test_no_match_empty(self):
        assert find_context("hello world", "xyz") == []

    def test_single_match(self):
        results = find_context("hello world", "world")
        assert len(results) == 1
        assert "world" in results[0]["snippet"]
        assert results[0]["offset_start"] == 6
        assert results[0]["offset_end"] == 11

    def test_multiple_matches(self):
        results = find_context("foo bar foo baz foo", "foo", context_chars=5)
        assert len(results) == 3
        offsets = [r["offset_start"] for r in results]
        assert offsets == [0, 8, 16]

    def test_case_insensitive(self):
        results = find_context("Hello WORLD hello", "hello")
        assert len(results) == 2


class TestSearchTranscript:
    def test_finds_needle_alpha_user(self):
        results = search_transcript(FIXTURE, ["NEEDLE-ALPHA"], type_filter="user")
        assert len(results) == 1
        assert results[0]["line_num"] == 5
        assert results[0]["uuid"] == "u-003"

    def test_finds_needle_beta_assistant(self):
        results = search_transcript(FIXTURE, ["NEEDLE-BETA"], type_filter="assistant")
        assert len(results) == 1
        assert results[0]["uuid"] == "a-004"

    def test_and_search(self):
        # Both terms must appear in the same line (line 5: "magic phrase NEEDLE-ALPHA")
        results = search_transcript(FIXTURE, ["magic", "NEEDLE-ALPHA"])
        assert len(results) == 1

    def test_and_search_no_match(self):
        # NEEDLE-ALPHA is on line 5, NEEDLE-BETA is on line 10. No line has both.
        results = search_transcript(FIXTURE, ["NEEDLE-ALPHA", "NEEDLE-BETA"])
        assert results == []

    def test_type_filter_user_only(self):
        results = search_transcript(FIXTURE, ["NEEDLE"], type_filter="user")
        # "NEEDLE-ALPHA" is on user line 5; "NEEDLE-BETA" is on user line 10.
        assert len(results) == 2

    def test_type_filter_assistant_only(self):
        results = search_transcript(FIXTURE, ["NEEDLE"], type_filter="assistant")
        # NEEDLE-BETA appears in assistant line 11.
        assert len(results) == 1
        assert results[0]["uuid"] == "a-004"

    def test_invalid_type_filter_raises(self):
        with pytest.raises(ValueError):
            search_transcript(FIXTURE, ["x"], type_filter="bogus")

    def test_corrupt_skip(self, tmp_path):
        p = tmp_path / "corrupt.jsonl"
        p.write_text(
            '{"type":"user","uuid":"u1","message":{"content":"good"}}\n'
            'this is not json\n'
            '{"type":"user","uuid":"u2","message":{"content":"alsogood"}}\n',
            encoding="utf-8",
        )
        # Skip mode: corrupt line is silently dropped.
        results = search_transcript(p, ["good"], on_corrupt="skip")
        # Both "good" and "alsogood" contain "good" -- 2 user matches.
        assert len(results) == 2

    def test_corrupt_raise(self, tmp_path):
        p = tmp_path / "corrupt.jsonl"
        p.write_text(
            '{"type":"user","uuid":"u1","message":{"content":"good"}}\n'
            'this is not json\n',
            encoding="utf-8",
        )
        with pytest.raises(CorruptJSONLError):
            search_transcript(p, ["good"], on_corrupt="raise")

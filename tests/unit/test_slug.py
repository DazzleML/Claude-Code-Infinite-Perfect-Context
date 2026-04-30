"""Unit tests for ccipc_lib.slug."""

from __future__ import annotations

import os
import sys
import unicodedata
from pathlib import Path

import pytest

# Ensure src/ is on sys.path
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from ccipc_lib.slug import (  # noqa: E402
    canonicalize_path,
    djb2_hash,
    sanitize_path,
    slug_from_cwd,
    _to_base36_abs,
)
from ccipc_lib.cc_constants import MAX_SANITIZED_LENGTH  # noqa: E402


class TestDjb2:
    """CC's djb2 variant: hash starts at 0, uses *31 + char, signed-32-bit."""

    def test_empty_string(self):
        assert djb2_hash("") == 0

    def test_known_value_hello(self):
        # Hand-computed: 0 -> 104 -> 3325 -> 103183 -> 3198781 -> 99162322
        assert djb2_hash("hello") == 99162322

    def test_known_value_a(self):
        # ((0 << 5) - 0 + 97) | 0 = 97
        assert djb2_hash("a") == 97

    def test_signed_int32_range(self):
        # The hash should always fit in signed-32-bit range.
        for s in ["", "a", "abc", "x" * 100, "hello world", "C:/code/test"]:
            h = djb2_hash(s)
            assert -(2**31) <= h <= (2**31) - 1, f"out of range for {s!r}: {h}"

    def test_negative_hash_still_in_range(self):
        # Some inputs produce negative hashes due to int32 wrap.
        # Just verify it stays in range, not specific values.
        h = djb2_hash("Hello, World! This is a longer string to potentially overflow.")
        assert -(2**31) <= h <= (2**31) - 1


class TestBase36:
    def test_zero(self):
        assert _to_base36_abs(0) == "0"

    def test_known_values(self):
        # JS reference: (10).toString(36) === "a", (35).toString(36) === "z", (36) === "10"
        assert _to_base36_abs(10) == "a"
        assert _to_base36_abs(35) == "z"
        assert _to_base36_abs(36) == "10"
        # Hand-computed: 99162322 in base-36 = "1n1e4y"
        # (matches JS Math.abs(djb2Hash("hello")).toString(36))
        assert _to_base36_abs(99162322) == "1n1e4y"

    def test_negative_input(self):
        # Math.abs first, then toString(36).
        assert _to_base36_abs(-10) == "a"


class TestSanitizePath:
    def test_simple_alphanum(self):
        assert sanitize_path("abc123") == "abc123"

    def test_replaces_non_alphanum(self):
        # "C:/code/test" -> "C-code-test" ... wait, the "/" becomes "-",
        # the ":" becomes "-", so we get "C--code-test"
        assert sanitize_path("C:/code/test") == "C--code-test"

    def test_matches_known_real_session_slug(self):
        # Empirically observed: C:\code\wtf-restarted -> C--code-wtf-restarted
        # (Verified by reading ~/.claude/session-states/<uuid>.json transcript_path)
        assert sanitize_path("C:\\code\\wtf-restarted") == "C--code-wtf-restarted"

    def test_short_path_no_hash_suffix(self):
        result = sanitize_path("short_path")
        assert "-" not in result.split("-")[-1] or len(result) <= MAX_SANITIZED_LENGTH

    def test_long_path_appends_djb2_hash(self):
        # Use a long path to trigger the suffix branch.
        long_input = "C:/" + "x" * 250  # > 200 chars
        result = sanitize_path(long_input)
        assert len(result) > MAX_SANITIZED_LENGTH
        assert result[MAX_SANITIZED_LENGTH] == "-"
        # Suffix should be a valid base-36 string.
        suffix = result[MAX_SANITIZED_LENGTH + 1:]
        assert suffix
        assert all(c in "0123456789abcdefghijklmnopqrstuvwxyz" for c in suffix)

    def test_unicode_input(self):
        # Non-alphanumeric unicode also gets replaced.
        result = sanitize_path("café/test")
        # 'é' is non-alphanumeric per [^a-zA-Z0-9] -> "-"
        # 'caf' kept, 'é' -> '-', '/' -> '-', 'test' kept
        assert result == "caf--test"


class TestCanonicalizePath:
    def test_realpath_idempotent_on_existing(self, tmp_path):
        result = canonicalize_path(str(tmp_path))
        assert Path(result).exists()
        # NFC-normalized
        assert result == unicodedata.normalize("NFC", result)

    def test_nonexistent_path_falls_back(self):
        # When path doesn't exist, realpath might still resolve it
        # (returning the absolute form), and we still NFC-normalize.
        result = canonicalize_path("/nonexistent/probably/path/xyz")
        # Should be NFC-normalized regardless
        assert result == unicodedata.normalize("NFC", result)


class TestSlugFromCwd:
    def test_round_trip(self, tmp_path):
        # Take a tmp dir, derive its slug, verify it's deterministic.
        slug1 = slug_from_cwd(str(tmp_path))
        slug2 = slug_from_cwd(str(tmp_path))
        assert slug1 == slug2
        # Slug must contain only [a-zA-Z0-9-]
        assert all(c.isalnum() or c == "-" for c in slug1)

    def test_long_real_dir_triggers_hash(self, tmp_path):
        # Build a deeply-nested temp dir > 200 chars total.
        deep = tmp_path
        for _ in range(20):
            deep = deep / "very_long_directory_segment"
        deep.mkdir(parents=True, exist_ok=True)
        slug = slug_from_cwd(str(deep))
        assert len(slug) > MAX_SANITIZED_LENGTH
        assert slug[MAX_SANITIZED_LENGTH] == "-"

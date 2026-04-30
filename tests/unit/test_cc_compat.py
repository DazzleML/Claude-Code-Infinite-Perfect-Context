"""Unit tests for ccipc_lib.cc_compat."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from ccipc_lib.cc_compat import (  # noqa: E402
    CCVersion,
    assert_cassette_compatible,
    is_compatible,
    parse_cc_version,
)
from ccipc_lib.errors import CCVersionIncompatibleError  # noqa: E402


class TestParse:
    def test_bare_version(self):
        v = parse_cc_version("2.5.1")
        assert v == CCVersion(major=2, minor=5, patch=1, suffix="", raw="2.5.1")

    def test_with_prefix(self):
        v = parse_cc_version("claude 2.5.1")
        assert v.major == 2
        assert v.minor == 5
        assert v.patch == 1

    def test_with_suffix(self):
        v = parse_cc_version("2.5.1-beta.3")
        assert v.major == 2
        assert v.suffix == "-beta.3"

    def test_with_prefix_and_suffix(self):
        v = parse_cc_version("Claude Code v2.5.1-rc1")
        assert (v.major, v.minor, v.patch) == (2, 5, 1)

    def test_no_match_returns_none(self):
        assert parse_cc_version("no version here") is None
        assert parse_cc_version("") is None
        assert parse_cc_version(None) is None  # type: ignore[arg-type]

    def test_str_roundtrip(self):
        v = parse_cc_version("2.5.1")
        assert str(v) == "2.5.1"
        v2 = parse_cc_version("2.5.1-beta")
        assert str(v2) == "2.5.1-beta"


class TestIsCompatible:
    def test_exact_match(self):
        a = CCVersion(2, 5, 1, "", "")
        b = CCVersion(2, 5, 1, "", "")
        assert is_compatible(a, b)

    def test_cassette_minor_less_than_current(self):
        cassette = CCVersion(2, 4, 9, "", "")
        current = CCVersion(2, 5, 0, "", "")
        assert is_compatible(cassette, current)  # 2.4 OK with 2.5

    def test_cassette_minor_greater_than_current(self):
        cassette = CCVersion(2, 6, 0, "", "")
        current = CCVersion(2, 5, 0, "", "")
        assert not is_compatible(cassette, current)  # CC was downgraded

    def test_different_major(self):
        cassette = CCVersion(2, 5, 0, "", "")
        current = CCVersion(3, 0, 0, "", "")
        assert not is_compatible(cassette, current)

    def test_patch_does_not_block(self):
        # Patch differences don't matter -- only major and minor are gated.
        cassette = CCVersion(2, 5, 99, "", "")
        current = CCVersion(2, 5, 0, "", "")
        assert is_compatible(cassette, current)


class TestAssertCompatible:
    def test_no_current_skips(self):
        # If we can't detect current CC, we don't block.
        with patch("ccipc_lib.cc_compat.get_installed_cc_version", return_value=None):
            assert_cassette_compatible("2.5.1")  # should not raise

    def test_no_cassette_version_skips(self):
        # If cassette has no version recorded (legacy), we don't block.
        with patch(
            "ccipc_lib.cc_compat.get_installed_cc_version",
            return_value=CCVersion(2, 5, 0, "", ""),
        ):
            assert_cassette_compatible("")  # should not raise
            assert_cassette_compatible(None)  # type: ignore[arg-type]

    def test_compatible_passes(self):
        with patch(
            "ccipc_lib.cc_compat.get_installed_cc_version",
            return_value=CCVersion(2, 5, 0, "", ""),
        ):
            assert_cassette_compatible("2.5.0")  # exact -> ok

    def test_incompatible_raises(self):
        with patch(
            "ccipc_lib.cc_compat.get_installed_cc_version",
            return_value=CCVersion(2, 5, 0, "", ""),
        ):
            with pytest.raises(CCVersionIncompatibleError):
                assert_cassette_compatible("3.0.0")

    def test_force_warns_instead_of_raising(self, capsys):
        with patch(
            "ccipc_lib.cc_compat.get_installed_cc_version",
            return_value=CCVersion(2, 5, 0, "", ""),
        ):
            assert_cassette_compatible("3.0.0", force=True)  # should not raise
            captured = capsys.readouterr()
            assert "Warning" in captured.err

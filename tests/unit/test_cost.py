"""Unit tests for ccipc_lib.cost."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from ccipc_lib.cost import (  # noqa: E402
    compute_compaction_warnings,
    compute_plan_warnings,
    estimate_cost_usd,
    estimate_tokens_from_bytes,
    estimate_tokens_from_path,
    resolve_model,
)
from ccipc_lib.cc_constants import (  # noqa: E402
    DEFAULT_MODEL,
    PLAN_QUOTAS_5H_TOKENS,
    PRICING_INPUT_USD_PER_M,
)


class TestTokenEstimation:
    def test_bytes_div_2(self):
        assert estimate_tokens_from_bytes(0) == 0
        assert estimate_tokens_from_bytes(1) == 0  # integer div
        assert estimate_tokens_from_bytes(2) == 1
        assert estimate_tokens_from_bytes(1000) == 500
        assert estimate_tokens_from_bytes(1_000_000) == 500_000

    def test_from_path(self, tmp_path):
        f = tmp_path / "x.bin"
        f.write_bytes(b"x" * 1000)
        assert estimate_tokens_from_path(f) == 500


class TestResolveModel:
    def test_explicit_cli_wins(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_MODEL", "env-model")
        m, src = resolve_model("claude-sonnet-4-5")
        assert m == "claude-sonnet-4-5"
        assert src == "--model_flag"

    def test_env_var_when_no_cli(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        m, src = resolve_model(None)
        assert m == "claude-sonnet-4-6"
        assert "env" in src

    def test_default_when_neither(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        m, src = resolve_model(None)
        assert m == DEFAULT_MODEL
        assert src == "default"


class TestEstimateCostUsd:
    def test_known_model_pricing(self):
        # claude-sonnet-4-5 = $3.00 / M input tokens
        cost = estimate_cost_usd(1_000_000, "claude-sonnet-4-5")
        assert abs(cost - 3.00) < 1e-6

    def test_partial_million(self):
        cost = estimate_cost_usd(500_000, "claude-sonnet-4-5")
        assert abs(cost - 1.50) < 1e-6

    def test_unknown_model_returns_zero(self):
        assert estimate_cost_usd(1_000_000, "unknown-model-xyz") == 0.0


class TestPlanWarnings:
    def test_max5_blocked_when_too_big(self):
        # Max5 is ~88K. 100K should block.
        warnings = compute_plan_warnings(100_000)
        max5 = next(w for w in warnings if w["plan"] == "max5")
        assert max5["would_block"] is True
        assert max5["would_consume_pct"] > 100

    def test_max5_safe_when_small(self):
        warnings = compute_plan_warnings(10_000)
        max5 = next(w for w in warnings if w["plan"] == "max5")
        assert max5["would_block"] is False
        assert max5["would_consume_pct"] < 50

    def test_api_unbounded(self):
        # API has no 5h cap, should never block.
        warnings = compute_plan_warnings(500_000)
        api = next(w for w in warnings if w["plan"] == "api")
        assert api["would_block"] is False
        assert api["budget_tokens"] is None

    def test_all_plans_present(self):
        warnings = compute_plan_warnings(50_000)
        plans = {w["plan"] for w in warnings}
        assert plans == set(PLAN_QUOTAS_5H_TOKENS.keys())


class TestCompactionWarnings:
    def test_no_warning_well_below_threshold(self):
        # 1K tokens for sonnet (167K threshold) -> no warning.
        warnings = compute_compaction_warnings(1_000, "claude-sonnet-4-5")
        assert warnings == []

    def test_medium_warning_within_10pct(self):
        # 90% of 167K = ~150K -> medium warning.
        warnings = compute_compaction_warnings(155_000, "claude-sonnet-4-5")
        assert any(w["severity"] == "medium" for w in warnings)

    def test_high_warning_at_threshold(self):
        # Exactly the threshold -> high.
        warnings = compute_compaction_warnings(167_000, "claude-sonnet-4-5")
        assert any(w["severity"] == "high" for w in warnings)

    def test_fatal_above_blocking_limit(self):
        # 200K is above 177K blocking limit for sonnet.
        warnings = compute_compaction_warnings(200_000, "claude-sonnet-4-5")
        assert any(w["severity"] == "fatal" for w in warnings)

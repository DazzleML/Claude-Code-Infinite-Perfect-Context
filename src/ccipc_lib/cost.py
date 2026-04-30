"""Cost estimation for ccipc cassettes.

Two cost models surfaced to users:

1. **API cost in USD** -- the simple raw-price calculation. Useful for
   API-direct users who pay per token.

2. **Plan budget impact** -- for Max5 / Max20 users, the API price is
   irrelevant. What matters is what fraction of their 5h window the
   cassette will consume. This is the primary use case per the user's
   note in the original /collaborate3 brief.

Token estimation uses CC's own heuristic of `len(bytes) / 2`. This is
intentionally crude; the actual tokenizer would require a network call
or shipping a tiktoken/anthropic-tokens dependency. For Phase 1 the
heuristic is fine -- we're estimating, not billing.

Pricing constants live in cc_constants.PRICING_INPUT_USD_PER_M with a
PRICING_AS_OF date for users to verify against current Anthropic prices.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ccipc_lib.cc_constants import (
    DEFAULT_MODEL,
    PLAN_QUOTAS_5H_TOKENS,
    PRICING_AS_OF,
    PRICING_INPUT_USD_PER_M,
    TOKEN_HEURISTIC_BYTES_PER_TOKEN,
    get_autocompact_threshold,
    get_blocking_limit,
    get_effective_context_window,
)


@dataclass
class CostEstimate:
    """Result of estimating a cassette's cost."""

    estimated_tokens: int
    estimated_cost_usd: float
    model: str
    model_source: str  # "default" | "ANTHROPIC_MODEL_env" | "--model_flag"
    pricing_basis: str  # "input_only" for now
    pricing_as_of: str
    plan_warnings: list[dict]  # [{"plan": "max5", "would_consume_pct": 99.1, "would_block": True}, ...]
    compaction_warnings: list[dict]  # [{"threshold_pct": 87.5}, ...]


def resolve_model(
    cli_model: Optional[str] = None,
    env_var_name: str = "ANTHROPIC_MODEL",
) -> tuple[str, str]:
    """Resolve which model to use for cost estimation.

    Resolution order:
        1. cli_model (--model flag)
        2. environment variable (default: ANTHROPIC_MODEL)
        3. cc_constants.DEFAULT_MODEL

    Returns:
        (model_id, source) where source is "--model_flag" | "<ENV>_env" | "default".
    """
    if cli_model:
        return cli_model, "--model_flag"
    env_val = os.environ.get(env_var_name)
    if env_val:
        return env_val, f"{env_var_name}_env"
    return DEFAULT_MODEL, "default"


def estimate_tokens_from_bytes(byte_size: int) -> int:
    """CC's heuristic: tokens ≈ bytes / 2.

    Conservative -- real tokenization is more like bytes / 3.5 for English,
    but CC uses /2 for its own estimates so we match it.
    """
    return byte_size // TOKEN_HEURISTIC_BYTES_PER_TOKEN


def estimate_tokens_from_path(cassette_path: str | Path) -> int:
    """Apply the heuristic to an on-disk cassette JSONL."""
    return estimate_tokens_from_bytes(os.path.getsize(cassette_path))


def estimate_cost_usd(tokens: int, model: str) -> float:
    """USD cost for `tokens` of input on `model`.

    Returns 0.0 if the model isn't in PRICING_INPUT_USD_PER_M (and emits
    a stderr warning -- but that's the caller's job here).
    """
    rate = PRICING_INPUT_USD_PER_M.get(model)
    if rate is None:
        return 0.0
    return (tokens / 1_000_000) * rate


def compute_plan_warnings(tokens: int) -> list[dict]:
    """Build per-plan warning records describing how this cassette fits.

    Returns a list of dicts (one per plan) with:
        - plan: str
        - budget_tokens: int | None
        - would_consume_pct: float | None
        - would_block: bool  (True if cassette > plan's 5h budget)
    """
    warnings: list[dict] = []
    for plan, budget in PLAN_QUOTAS_5H_TOKENS.items():
        if budget is None:
            warnings.append({
                "plan": plan,
                "budget_tokens": None,
                "would_consume_pct": None,
                "would_block": False,
            })
            continue
        pct = (tokens / budget) * 100
        warnings.append({
            "plan": plan,
            "budget_tokens": budget,
            "would_consume_pct": round(pct, 1),
            "would_block": tokens > budget,
        })
    return warnings


def compute_compaction_warnings(tokens: int, model: str) -> list[dict]:
    """Build warnings about how close this cassette is to compaction thresholds.

    Returns a list of warning dicts. Empty list = no concerns.
    """
    warnings: list[dict] = []
    threshold = get_autocompact_threshold(model)
    blocking = get_blocking_limit(model)
    effective = get_effective_context_window(model)

    pct_of_threshold = (tokens / threshold) * 100 if threshold else 0
    pct_of_blocking = (tokens / blocking) * 100 if blocking else 0
    pct_of_effective = (tokens / effective) * 100 if effective else 0

    if tokens >= blocking:
        warnings.append({
            "severity": "fatal",
            "kind": "blocking_limit_exceeded",
            "tokens": tokens,
            "blocking_limit": blocking,
            "message": (
                "Cassette exceeds the hard blocking limit -- claude --resume will refuse "
                "to load it."
            ),
        })
    elif tokens >= threshold:
        warnings.append({
            "severity": "high",
            "kind": "autocompact_threshold_exceeded",
            "tokens": tokens,
            "threshold": threshold,
            "pct_of_threshold": round(pct_of_threshold, 1),
            "message": (
                "Cassette exceeds the autocompact threshold; CC will compact "
                "immediately on the first turn after hydrate (potential session-break risk)."
            ),
        })
    elif pct_of_threshold >= 90:
        warnings.append({
            "severity": "medium",
            "kind": "approaching_autocompact_threshold",
            "tokens": tokens,
            "threshold": threshold,
            "pct_of_threshold": round(pct_of_threshold, 1),
            "message": (
                "Cassette is within 10% of the autocompact threshold; "
                "increase --headroom-tokens to leave more room for new turns."
            ),
        })

    return warnings


def estimate_cassette_cost(
    cassette_path: str | Path,
    *,
    model: Optional[str] = None,
) -> CostEstimate:
    """Compute the full cost estimate for a cassette.

    Args:
        cassette_path: Path to a cassette JSONL on disk.
        model: Model id; if None, resolved via resolve_model().

    Returns:
        A CostEstimate with token count, USD cost, plan warnings, and
        compaction warnings populated.
    """
    resolved_model, source = resolve_model(model)
    tokens = estimate_tokens_from_path(cassette_path)
    cost = estimate_cost_usd(tokens, resolved_model)

    return CostEstimate(
        estimated_tokens=tokens,
        estimated_cost_usd=cost,
        model=resolved_model,
        model_source=source,
        pricing_basis="input_only",
        pricing_as_of=PRICING_AS_OF,
        plan_warnings=compute_plan_warnings(tokens),
        compaction_warnings=compute_compaction_warnings(tokens, resolved_model),
    )

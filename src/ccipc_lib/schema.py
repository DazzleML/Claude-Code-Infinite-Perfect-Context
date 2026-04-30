"""JSONL output schemas for ccipc tools.

Each tool emits one JSONL record per result on stdout. Records flat-merge
through the pipeline: each tool adds fields to the upstream record without
removing or renaming existing ones (per Round 2 endorsement).

Field naming uses domain prefixes to prevent collisions:

    source_*    -- where the data came from (search hit metadata)
    boundary_*  -- find-boundary additions
    cassette_*  -- cassette additions
    cost_*      -- cost-estimate additions
    hydrate_*   -- hydrate additions
    ccipc_*     -- ccipc-internal metadata (schema version, lineage, etc.)

The ccipc_schema_version is a hard versioning token. Bump on any
breaking schema change.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

CCIPC_SCHEMA_VERSION = "0.1"


# ---------------------------------------------------------------------------
# Stage 1: search output
# ---------------------------------------------------------------------------

@dataclass
class SearchHit:
    """One search hit, emitted by `ccipc search`."""

    session_id: str
    jsonl_path: str
    line_num: int
    uuid: str
    type: str  # "user" | "assistant" | "system" | "attachment"
    snippet: str
    score: float = 1.0
    matched_terms: list[str] = field(default_factory=list)
    parent_uuid: Optional[str] = None
    is_sidechain: bool = False
    snippet_offset_start: Optional[int] = None
    snippet_offset_end: Optional[int] = None

    def to_record(self) -> dict:
        return {
            "ccipc_schema_version": CCIPC_SCHEMA_VERSION,
            "tool": "search",
            "session_id": self.session_id,
            "jsonl_path": self.jsonl_path,
            "line_num": self.line_num,
            "uuid": self.uuid,
            "type": self.type,
            "snippet": self.snippet,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "parent_uuid": self.parent_uuid,
            "is_sidechain": self.is_sidechain,
            "snippet_offset_start": self.snippet_offset_start,
            "snippet_offset_end": self.snippet_offset_end,
        }


# ---------------------------------------------------------------------------
# Stage 2: find-boundary additions
# ---------------------------------------------------------------------------

def add_boundary_fields(
    record: dict,
    *,
    boundary_line_num: int,
    boundary_uuid: str,
    boundary_type: str,
    turn_count: int,
    preceding_lines: int,
    estimated_tokens_to_boundary: int,
    headroom_target_tokens: int,
) -> dict:
    """Mutate-then-return: add boundary_* fields to an upstream search record.

    Fan-in: this is called once per upstream record. find-boundary may be
    invoked with stdin containing many records; each gets enriched.
    """
    record = dict(record)  # shallow copy
    record.update({
        "tool": "find-boundary",  # overwrites the upstream "tool" key
        "boundary_line_num": boundary_line_num,
        "boundary_uuid": boundary_uuid,
        "boundary_type": boundary_type,  # "user_turn" | "compact_hard_stop" | "session_start"
        "turn_count": turn_count,
        "preceding_lines": preceding_lines,
        "estimated_tokens_to_boundary": estimated_tokens_to_boundary,
        "headroom_target_tokens": headroom_target_tokens,
    })
    return record


# ---------------------------------------------------------------------------
# Stage 3: cassette additions
# ---------------------------------------------------------------------------

def add_cassette_fields(
    record: dict,
    *,
    cassette_path: str,
    new_uuid: str,
    source_session_id: str,
    boundary_uuid: str,
    lines_copied: int,
    byte_size: int,
    estimated_tokens: int,
    mode: str,
    cc_version_when_made: str,
    ccipc_version: str,
) -> dict:
    record = dict(record)
    record.update({
        "tool": "cassette",
        "cassette_path": cassette_path,
        "cassette_new_uuid": new_uuid,
        "cassette_source_session_id": source_session_id,
        "cassette_boundary_uuid": boundary_uuid,
        "cassette_lines_copied": lines_copied,
        "cassette_byte_size": byte_size,
        "cassette_estimated_tokens": estimated_tokens,
        "cassette_mode": mode,
        "cassette_cc_version_when_made": cc_version_when_made,
        "cassette_ccipc_version": ccipc_version,
    })
    return record


# ---------------------------------------------------------------------------
# Stage 4: cost-estimate additions
# ---------------------------------------------------------------------------

def add_cost_fields(
    record: dict,
    *,
    estimated_tokens: int,
    cost_usd: float,
    model: str,
    model_source: str,
    pricing_basis: str,
    pricing_as_of: str,
    plan_warnings: list[dict],
    compaction_warnings: list[dict],
) -> dict:
    record = dict(record)
    record.update({
        "tool": "cost-estimate",
        "cost_estimated_tokens": estimated_tokens,
        "cost_usd": cost_usd,
        "cost_model": model,
        "cost_model_source": model_source,
        "cost_pricing_basis": pricing_basis,
        "cost_pricing_as_of": pricing_as_of,
        "cost_plan_warnings": plan_warnings,
        "cost_compaction_warnings": compaction_warnings,
    })
    return record


# ---------------------------------------------------------------------------
# Stage 5: hydrate additions
# ---------------------------------------------------------------------------

def add_hydrate_fields(
    record: dict,
    *,
    installed_path: str,
    new_session_id: str,
    claude_invocation: list[str],
    exit_code: int,
    duration_seconds: float,
) -> dict:
    record = dict(record)
    record.update({
        "tool": "hydrate",
        "hydrate_installed_path": installed_path,
        "hydrate_new_session_id": new_session_id,
        "hydrate_claude_invocation": list(claude_invocation),
        "hydrate_exit_code": exit_code,
        "hydrate_duration_seconds": duration_seconds,
    })
    return record


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def emit_record(record: dict, *, stream=sys.stdout) -> None:
    """Write a single JSONL record + newline to `stream`. Flushes at end."""
    json.dump(record, stream, ensure_ascii=False)
    stream.write("\n")
    stream.flush()


def read_records(stream) -> list[dict]:
    """Read all JSONL records from `stream`. Skips blank lines.

    Returns the list eagerly so callers can know `len(records)` for
    pipeline-fan-in checks before processing any of them.

    Raises:
        ValueError: on a malformed JSONL line.
    """
    records: list[dict] = []
    for line_num, line in enumerate(stream, 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"malformed JSONL on stdin line {line_num}: {e}"
            ) from e
        if isinstance(obj, dict):
            records.append(obj)
    return records


def reject_if_multiple(records: list[dict], tool_name: str) -> dict:
    """Pipeline fan-in guard for single-target tools (cassette, hydrate).

    Per Round 2 design (Gemini's catch): cassette and hydrate must refuse
    >1 stdin record explicitly rather than silently picking the first one.

    Args:
        records: List of upstream JSONL records.
        tool_name: Tool emitting the error (used in the error message).

    Returns:
        The single record, when len(records) == 1.

    Raises:
        PipelineFanInError: If len(records) != 1.
        ValueError: If len(records) == 0 (caller should normally check first).
    """
    from ccipc_lib.errors import PipelineFanInError  # local import: avoid cycle

    if len(records) == 0:
        raise ValueError(f"{tool_name}: no input records on stdin")
    if len(records) > 1:
        raise PipelineFanInError(tool_name=tool_name, record_count=len(records))
    return records[0]

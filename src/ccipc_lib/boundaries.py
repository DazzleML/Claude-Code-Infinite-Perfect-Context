"""Turn-boundary classification for ccipc.

A "boundary" is the JSONL line where a cassette's verbatim prefix should
END. Picking a clean boundary matters because:

1. **Schema integrity**: Cassettes must end at a complete user turn, not
   in the middle of a tool-use sequence. Otherwise CC's parser may reject
   the cassette or behave unpredictably on resume.

2. **Headroom**: We want the cassette to leave enough free token budget
   that the new session can do useful work without immediately triggering
   compaction (the MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3 circuit
   breaker can permanently break sessions if we cut too close).

3. **Compaction boundaries**: CC writes a SystemCompactBoundaryMessage
   line when it auto-compacts. Walking past these (forward) would bring
   in pre-compacted content that CC explicitly summarized away. Default
   behavior is to treat these as hard stops; --include-pre-compact opts
   in to crossing them (Phase 1 supports detection; the override is wired
   in at find-boundary's CLI).

A boundary is a JSONL line satisfying:
    - type == "user"
    - isSidechain == False (sidechains are agent-to-agent calls, not user input)
    - line is not after a SystemCompactBoundaryMessage we're hard-stopping at
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from ccipc_lib.cc_constants import (
    SYSTEM_COMPACT_BOUNDARY_TYPE,
    TOKEN_HEURISTIC_BYTES_PER_TOKEN,
)
from ccipc_lib.errors import CorruptJSONLError


class BoundaryType(str, Enum):
    """Why this line was chosen as a boundary."""

    USER_TURN = "user_turn"
    COMPACT_HARD_STOP = "compact_hard_stop"
    SESSION_START = "session_start"


@dataclass
class Boundary:
    """A boundary candidate within a JSONL transcript."""

    line_num: int           # 1-indexed
    uuid: str
    boundary_type: BoundaryType
    parent_uuid: Optional[str] = None
    is_sidechain: bool = False
    estimated_tokens_to_boundary: int = 0  # bytes from start to boundary line / 2
    preceding_lines: int = 0
    raw_obj: dict = field(default_factory=dict)


def _is_user_turn_boundary(obj: dict) -> bool:
    """True if `obj` is a clean user-turn boundary candidate."""
    if obj.get("type") != "user":
        return False
    if obj.get("isSidechain", False):
        return False
    return True


def _is_compact_boundary(obj: dict) -> bool:
    """True if `obj` is a SystemCompactBoundaryMessage."""
    return obj.get("type") == SYSTEM_COMPACT_BOUNDARY_TYPE


def find_boundary_before(
    jsonl_path: str | Path,
    target_line_num: int,
    *,
    headroom_tokens: int = 30_000,
    include_pre_compact: bool = False,
    on_corrupt: str = "skip",
) -> Optional[Boundary]:
    """Walk backward from `target_line_num` to find the nearest user-turn boundary.

    The boundary is the cleanest place to END a Mode-A cassette so that:
        - The cassette finishes on a complete user turn.
        - The cassette's estimated token count leaves at least
          `headroom_tokens` of room before the autocompact threshold.

    Args:
        jsonl_path: Path to the source session JSONL.
        target_line_num: The 1-indexed line number of the search hit. Walk
            backward from here.
        headroom_tokens: Minimum free token budget to preserve at the end of
            the cassette. The chosen boundary is the latest user-turn that
            still leaves this much room before autocompact.
        include_pre_compact: If True, walk past SystemCompactBoundaryMessage
            lines. Default False -- compaction boundaries are hard stops.
        on_corrupt: "skip" (default) ignores malformed lines; "raise" raises
            CorruptJSONLError on the first one.

    Returns:
        A Boundary describing the chosen line, or None if no suitable
        boundary exists (e.g. the file is empty or has no user turns).
    """
    jsonl_path = Path(jsonl_path)

    # First pass: read all lines into memory with byte offsets so we can
    # compute token estimates quickly. Session JSONLs are usually <100MB,
    # which is fine to hold in memory.
    lines: list[tuple[int, dict, int]] = []  # (line_num, parsed_obj, byte_offset_at_line_start)
    byte_offset = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    lines.append((line_num, obj, byte_offset))
            except json.JSONDecodeError as e:
                if on_corrupt == "raise":
                    raise CorruptJSONLError(
                        str(jsonl_path), line_num, parse_error=str(e)
                    ) from e
                # Skip malformed lines.
            # bytes consumed for this line including newline
            byte_offset += len(line.encode("utf-8"))

    if not lines:
        return None

    total_bytes = byte_offset

    # Find the index in `lines` corresponding to target_line_num. This may
    # not equal target_line_num itself if some lines were skipped as corrupt.
    target_idx = None
    for i, (ln, _, _) in enumerate(lines):
        if ln >= target_line_num:
            target_idx = i
            break
    if target_idx is None:
        target_idx = len(lines) - 1

    # Walk backward looking for a user-turn boundary.
    # Hard-stop at SystemCompactBoundaryMessage unless include_pre_compact.
    # Apply headroom: prefer the latest user-turn that leaves room.
    chosen: Optional[Boundary] = None

    for i in range(target_idx, -1, -1):
        line_num, obj, byte_offset_at_line = lines[i]

        # Hard stop at compact boundary?
        if _is_compact_boundary(obj) and not include_pre_compact:
            # If we hit a compact boundary BEFORE finding a usable user-turn,
            # the boundary IS the compact line itself.
            if chosen is None:
                chosen = Boundary(
                    line_num=line_num,
                    uuid=obj.get("uuid", ""),
                    boundary_type=BoundaryType.COMPACT_HARD_STOP,
                    parent_uuid=obj.get("parentUuid"),
                    is_sidechain=bool(obj.get("isSidechain", False)),
                    estimated_tokens_to_boundary=byte_offset_at_line // TOKEN_HEURISTIC_BYTES_PER_TOKEN,
                    preceding_lines=line_num - 1,
                    raw_obj=obj,
                )
            break

        if not _is_user_turn_boundary(obj):
            continue

        # This is a candidate user-turn boundary.
        # Compute headroom: bytes from start of file to (but not including)
        # the next line after this boundary. We use byte_offset_at_line as a
        # proxy for "everything BEFORE this line is the cassette".
        bytes_to_boundary = byte_offset_at_line
        tokens_to_boundary = bytes_to_boundary // TOKEN_HEURISTIC_BYTES_PER_TOKEN

        # We want to ensure (total_capacity - tokens_to_boundary) >= headroom_tokens.
        # In Phase 1 we treat the cassette ITSELF as the relevant size; the
        # caller passes the desired headroom and we pick the latest boundary
        # whose token count leaves them with that room.
        # Implementation: choose the FIRST candidate walking backward that's
        # close to but not exceeding (total_tokens - headroom_tokens).
        total_tokens = total_bytes // TOKEN_HEURISTIC_BYTES_PER_TOKEN
        max_acceptable = max(0, total_tokens - headroom_tokens)

        if tokens_to_boundary <= max_acceptable:
            chosen = Boundary(
                line_num=line_num,
                uuid=obj.get("uuid", ""),
                boundary_type=BoundaryType.USER_TURN,
                parent_uuid=obj.get("parentUuid"),
                is_sidechain=False,
                estimated_tokens_to_boundary=tokens_to_boundary,
                preceding_lines=line_num - 1,
                raw_obj=obj,
            )
            break

    # If we exhausted the walk without finding a boundary, fall back to the
    # session start (line 1 / no preceding cassette).
    if chosen is None:
        ln, obj, _ = lines[0]
        chosen = Boundary(
            line_num=ln,
            uuid=obj.get("uuid", ""),
            boundary_type=BoundaryType.SESSION_START,
            parent_uuid=obj.get("parentUuid"),
            is_sidechain=bool(obj.get("isSidechain", False)),
            estimated_tokens_to_boundary=0,
            preceding_lines=0,
            raw_obj=obj,
        )

    return chosen


def count_compact_boundaries(jsonl_path: str | Path) -> int:
    """How many SystemCompactBoundaryMessage lines exist in the JSONL.

    Useful for diagnostics and for showing the user how many compactions
    they have to navigate around.
    """
    count = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and _is_compact_boundary(obj):
                count += 1
    return count

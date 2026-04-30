"""JSONL full-text search across Claude Code session transcripts.

Verbatim port (with light Python-modernization) of csb's
scripts/search_sesslog.py functions extract_strings, find_context, and
search_transcript. The investigation phase confirmed these are NOT
importable from the installed csb package -- they live as standalone
scripts.

This module is the engine for `ccipc search`. The tool wrapper at
tools/core/search/ converts CLI args into calls here and emits results
as JSONL on stdout.

Differences from csb's original:

- Type annotations added.
- find_context returns a list[dict] with offsets, not just snippet strings,
  so downstream tools can highlight or extract char-ranges.
- search_transcript returns dicts with line_num, type, snippets (each a
  dict {snippet, offset_start, offset_end}), and the parsed JSON object's
  uuid (so find-boundary can chain).
- type_filter behavior tightened: matches against the JSONL `type` field
  ONLY (not raw line text), and validated against VALID_TRANSCRIPT_TYPES.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Optional

from ccipc_lib.cc_constants import VALID_TRANSCRIPT_TYPES
from ccipc_lib.errors import CorruptJSONLError


def extract_strings(
    obj: object, depth: int = 0, max_depth: int = 6
) -> Iterator[str]:
    """Recursively yield every string value in a nested JSON object.

    Mirrors csb's algorithm. Capped at max_depth to avoid runaway
    recursion on pathological structures.
    """
    if depth > max_depth:
        return
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from extract_strings(v, depth + 1, max_depth)
    elif isinstance(obj, list):
        for v in obj:
            yield from extract_strings(v, depth + 1, max_depth)


def find_context(
    text: str, term: str, context_chars: int = 150
) -> list[dict]:
    """Find all case-insensitive occurrences of `term` in `text`.

    Returns a list of dicts, each containing the surrounding-context
    snippet and the integer offsets within `text` where the match was
    found.

    Args:
        text: Haystack to search.
        term: Needle to find (case-insensitive).
        context_chars: Characters of surrounding context to include.

    Returns:
        List of dicts: [{"snippet": str, "offset_start": int, "offset_end": int}, ...]
    """
    results: list[dict] = []
    lower_text = text.lower()
    lower_term = term.lower()
    start = 0
    while True:
        idx = lower_text.find(lower_term, start)
        if idx == -1:
            break
        # Extract context window
        begin = max(0, idx - context_chars)
        end = min(len(text), idx + len(term) + context_chars)
        snippet = text[begin:end]
        # Clean up: trim to nearest newline boundaries when possible so the
        # snippet doesn't start mid-line (matches csb's behavior).
        if begin > 0:
            nl = snippet.find("\n")
            if nl != -1 and nl < context_chars:
                snippet = snippet[nl + 1:]
        if end < len(text):
            nl = snippet.rfind("\n")
            if nl != -1 and nl > len(snippet) - context_chars:
                snippet = snippet[:nl]
        results.append({
            "snippet": snippet.strip(),
            "offset_start": idx,
            "offset_end": idx + len(term),
        })
        start = idx + 1
    return results


def search_transcript(
    path: str | Path,
    terms: Iterable[str],
    *,
    context_chars: int = 150,
    type_filter: Optional[str] = None,
    on_corrupt: str = "skip",
) -> list[dict]:
    """Search a session JSONL for lines containing all of `terms`.

    AND-search: every term must appear in the line's combined string content
    (matched case-insensitively).

    Args:
        path: Path to the .jsonl transcript.
        terms: Iterable of search terms (all must match).
        context_chars: Characters of surrounding context per snippet.
        type_filter: If set, only match lines whose top-level "type" field
            equals this value. Must be one of VALID_TRANSCRIPT_TYPES.
        on_corrupt: "skip" (default) silently skips malformed lines.
            "raise" raises CorruptJSONLError on the first malformed line.

    Returns:
        List of match dicts:
            {
                "line_num": int,
                "type": str,
                "uuid": str,
                "parent_uuid": str | None,
                "is_sidechain": bool,
                "snippets": [{"snippet": str, "offset_start": int, "offset_end": int}],
            }

    Raises:
        FileNotFoundError: if `path` doesn't exist.
        CorruptJSONLError: if `on_corrupt="raise"` and a line fails to parse.
    """
    if type_filter is not None and type_filter not in VALID_TRANSCRIPT_TYPES:
        raise ValueError(
            f"type_filter must be one of {VALID_TRANSCRIPT_TYPES}, got {type_filter!r}"
        )

    terms_list = list(terms)
    if not terms_list:
        return []

    path = Path(path)
    matches: list[dict] = []

    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                if on_corrupt == "raise":
                    raise CorruptJSONLError(
                        str(path), line_num, parse_error=str(e)
                    ) from e
                continue

            if not isinstance(obj, dict):
                # Strange but not corrupt; skip.
                continue

            # Type filter operates on the top-level "type" field only.
            msg_type = obj.get("type", "")
            if type_filter is not None and msg_type != type_filter:
                continue

            # Collect all string content for AND-matching.
            all_text = "\n".join(extract_strings(obj))
            lower_all = all_text.lower()

            # AND-match: every term must appear.
            if all(t.lower() in lower_all for t in terms_list):
                # Snippets reference the FIRST term so users see what they
                # searched for; subsequent terms are conjunctive but not
                # individually highlighted.
                snippets = find_context(all_text, terms_list[0], context_chars)
                if snippets:
                    matches.append({
                        "line_num": line_num,
                        "type": msg_type,
                        "uuid": obj.get("uuid", ""),
                        "parent_uuid": obj.get("parentUuid"),
                        "is_sidechain": bool(obj.get("isSidechain", False)),
                        "snippets": snippets,
                    })

    return matches

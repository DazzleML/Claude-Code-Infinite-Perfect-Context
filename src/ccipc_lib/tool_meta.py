"""Helpers for tools to introspect their own .ccipc.json manifest.

Each tool ships with a `.ccipc.json` next to its script. The dispatcher
reads it for `ccipc list` / `ccipc info`. This module lets the tool
itself read the same manifest at runtime so its argparse `--help` text
can reuse the manifest's `description` instead of duplicating it.

Usage from a tool script (e.g., `tools/core/cassette/cassette.py`):

    from ccipc_lib.tool_meta import load_tool_manifest, get_description

    _MANIFEST = load_tool_manifest(__file__)
    _DESCRIPTION = get_description(_MANIFEST, fallback="...short summary...")

    p = argparse.ArgumentParser(description=_DESCRIPTION, ...)

The fallback string keeps the tool runnable in standalone or
pre-install scenarios where the manifest may not be locatable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union


def load_tool_manifest(tool_script_or_dir: Union[str, Path]) -> dict:
    """Load the .ccipc.json sitting next to the given tool script or dir.

    Accepts either a script path (e.g., `__file__`) or a directory.
    Returns the parsed manifest dict, or `{}` on any failure (missing
    file, malformed JSON, IO error). Callers should always provide a
    `fallback` to `get_description()` for that case.
    """
    p = Path(tool_script_or_dir)
    tool_dir = p.parent if p.is_file() else p
    manifest_path = tool_dir / ".ccipc.json"
    if not manifest_path.is_file():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def get_description(manifest: dict, *, fallback: str = "") -> str:
    """Return the manifest's description, or the fallback when absent."""
    desc = manifest.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc
    return fallback

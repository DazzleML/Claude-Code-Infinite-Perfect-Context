"""Main CLI entry point for ccipc.

Built on dazzlecmd-lib's AggregatorEngine. ccipc dispatches to tools
in tools/core/<name>/ that handle individual stages of the reverse-
compaction pipeline (search, find-boundary, cassette, hydrate, etc.).

Pipeline composition is at the shell level via stdin/stdout JSONL:

    ccipc search-multi --term X | ccipc find-boundary --before \\
      | ccipc cassette | ccipc hydrate

Mirrors the wtf-windows pattern (the canonical second adopter of
dazzlecmd-lib). Keep this file thin; tool logic lives in tools/core/*
and shared helpers live in src/ccipc_lib/.
"""

from __future__ import annotations

import os
import sys

from ccipc_lib._version import DISPLAY_VERSION, __version__
from dazzlecmd_lib import AggregatorEngine


def _build_ccipc_help(projects):
    """Build the help epilog with `commands:` and `<kit> tools:` sections.

    Mirrors the shape of `dz`'s top-level help so the family looks
    consistent. We list the lib-default meta-commands (kept all six;
    revisit later if any prove confusing) plus all discovered tools
    grouped by kit/namespace.
    """
    lines = []

    # Lib-default meta-commands. Kept hardcoded since the registry isn't
    # passed to the epilog builder; if we override or drop any, update here.
    lines.append("commands:")
    for cmd, desc in [
        ("list", "List available tools"),
        ("info <tool>", "Show detailed info about a tool"),
        ("kit", "Manage kits"),
        ("version", "Show version info"),
        ("tree", "Show the aggregator tree"),
        ("setup <tool>", "Run a tool's declared setup script"),
    ]:
        lines.append(f"  {cmd:<16}  {desc}")

    # Discovered tools, grouped by kit/namespace.
    if projects:
        namespaces = {}
        for project in projects:
            ns = project.get("namespace", "other")
            namespaces.setdefault(ns, []).append(project)
        for ns in sorted(namespaces.keys()):
            lines.append("")
            lines.append(f"{ns} tools:")
            for project in sorted(namespaces[ns], key=lambda p: p["name"]):
                name = project["name"]
                desc = project.get("description", "")
                # First sentence only, truncated for the table.
                if ". " in desc:
                    desc = desc[:desc.index(". ") + 1]
                max_desc = 56
                if len(desc) > max_desc:
                    desc = desc[:max_desc - 3] + "..."
                lines.append(f"  {name:<16}  {desc}")

    lines.append("")
    lines.append("Run 'ccipc <tool> --help' for tool-specific options.")
    lines.append("Pipe stages compose at the shell level: ccipc A | ccipc B | ccipc C")
    return "\n".join(lines)


def _find_ccipc_project_root():
    """Walk up from this file's location to find ccipc's repo root.

    The library's default find_project_root walks from the library's
    own __file__, which resolves to site-packages when installed.
    ccipc's tools/ and kits/ live next to its own cli.py source, so
    we start the walk from here. Mirrors wtf-windows' pattern.
    """
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
        if (os.path.isdir(os.path.join(current, "tools"))
                and os.path.isdir(os.path.join(current, "kits"))):
            return current
    return None


def main():
    """Main entry point for ccipc CLI."""
    engine = AggregatorEngine(
        name="ccipc",
        command="ccipc",
        tools_dir="tools",
        kits_dir="kits",
        manifest=".ccipc.json",
        description=(
            "ccipc -- Claude Code Infinite Perfect Context. "
            "Reverse compaction: search past conversation turns and "
            "auto-fork into them with full pre-compaction fidelity."
        ),
        version_info=(DISPLAY_VERSION, __version__),
        is_root=True,
        project_root=_find_ccipc_project_root(),
    )

    engine.epilog_builder = _build_ccipc_help

    return engine.run()


if __name__ == "__main__":
    sys.exit(main())

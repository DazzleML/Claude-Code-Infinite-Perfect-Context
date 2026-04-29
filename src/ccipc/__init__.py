"""ccipc -- Claude Code Infinite Perfect Context CLI dispatcher.

Built on dazzlecmd-lib's AggregatorEngine. Tools live in tools/core/<name>/
with .ccipc.json manifests; this package wires them together.
"""

from ccipc_lib._version import __version__, __app_name__

__all__ = ["__version__", "__app_name__"]

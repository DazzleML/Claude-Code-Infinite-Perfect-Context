"""ccipc_lib -- shared core for Claude Code Infinite Perfect Context.

Houses pure Python logic shared by all ccipc tools: JSONL parser,
csb client, cost estimator, cassette builder, fork-graph adapter.

The dispatcher (ccipc) and individual tools (tools/core/*) import from
this package. ccipc_lib has no CLI -- it is library code only.
"""

from ccipc_lib._version import __version__, __app_name__, PIP_VERSION

__all__ = ["__version__", "__app_name__", "PIP_VERSION"]

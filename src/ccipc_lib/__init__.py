"""ccipc_lib -- shared core for Claude Code Infinite Perfect Context.

Houses pure Python logic shared by all ccipc tools: JSONL parser,
csb client, cost estimator, cassette builder, fork-graph adapter.

The dispatcher (ccipc) and individual tools (tools/core/*) import from
this package. ccipc_lib has no CLI -- it is library code only.
"""

from ccipc_lib._version import (
    __app_name__,
    __version__,
    PIP_VERSION,
)

# Re-export the most common public symbols so tools can do:
#   from ccipc_lib import slug, errors, schema, ...
# rather than importing each submodule individually.

from ccipc_lib import (
    boundaries,
    cc_compat,
    cc_constants,
    config,
    cost,
    errors,
    jsonl_search,
    schema,
    slug,
)

__all__ = [
    "__app_name__",
    "__version__",
    "PIP_VERSION",
    # submodules
    "boundaries",
    "cc_compat",
    "cc_constants",
    "config",
    "cost",
    "errors",
    "jsonl_search",
    "schema",
    "slug",
]

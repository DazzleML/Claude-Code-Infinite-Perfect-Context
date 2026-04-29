"""Re-exports from ccipc_lib._version for convenience.

The canonical version source is src/ccipc_lib/_version.py.
This module exists so that `from ccipc._version import X` works the
same as `from ccipc_lib._version import X`. The repokit-common hook
chain edits the canonical file; this is a thin facade.
"""

from ccipc_lib._version import (
    MAJOR,
    MINOR,
    PATCH,
    PHASE,
    PROJECT_PHASE,
    __version__,
    __app_name__,
    get_version,
    get_base_version,
    get_display_version,
    get_pip_version,
    VERSION,
    BASE_VERSION,
    PIP_VERSION,
    DISPLAY_VERSION,
)

__all__ = [
    "MAJOR", "MINOR", "PATCH", "PHASE", "PROJECT_PHASE",
    "__version__", "__app_name__",
    "get_version", "get_base_version", "get_display_version", "get_pip_version",
    "VERSION", "BASE_VERSION", "PIP_VERSION", "DISPLAY_VERSION",
]

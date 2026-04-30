"""Claude Code version detection and cassette-compatibility checks.

Per Round 3 design: cassettes embed the CC version they were built for.
At hydrate-time we compare against the currently-installed CC and apply
the SemVer-aligned compat rule:

    cassette major == current major
    AND cassette minor <= current minor

This permits forward-minor compatibility (cassette built for CC 2.5,
user has CC 2.6 -- proceed) while refusing major-version mismatches and
downgrades (cassette built for CC 2.5, user has CC 2.4 -- refuse).

The `--force-cross-version-fork` escape hatch on hydrate bypasses this
check for users who know what they're doing.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

from ccipc_lib.errors import CCVersionIncompatibleError


# Match version strings like "claude 2.5.1", "Claude Code v2.5.1-beta", etc.
# Accepts optional leading text, requires major.minor.patch, allows optional
# pre-release/build suffix.
_VERSION_RE = re.compile(
    r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?P<suffix>[\w.+-]*)?"
)


@dataclass(frozen=True)
class CCVersion:
    """Parsed Claude Code version. Comparable via major/minor."""

    major: int
    minor: int
    patch: int
    suffix: str = ""
    raw: str = ""

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.suffix:
            s += self.suffix
        return s


def parse_cc_version(version_string: str) -> Optional[CCVersion]:
    """Parse a CC version string. Returns None if no version is found.

    Tolerates a wide range of formats:
        "2.5.1"
        "claude 2.5.1"
        "Claude Code v2.5.1"
        "2.5.1-beta.3"
        "2.5.1+build.4"
    """
    if not version_string:
        return None
    m = _VERSION_RE.search(version_string)
    if not m:
        return None
    return CCVersion(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        suffix=m.group("suffix") or "",
        raw=version_string.strip(),
    )


def get_installed_cc_version() -> Optional[CCVersion]:
    """Detect the currently-installed Claude Code version via `claude --version`.

    Returns None if `claude` is not on PATH or fails to report a version.
    Does NOT raise -- the caller decides how to handle absence (warn, fail,
    or skip the compat check).

    The subprocess uses a 5-second timeout; CC's --version is normally
    sub-second.
    """
    if shutil.which("claude") is None:
        return None
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    output = (result.stdout or "") + (result.stderr or "")
    return parse_cc_version(output)


def is_compatible(cassette: CCVersion, current: CCVersion) -> bool:
    """Apply the SemVer-aligned compat rule.

    Returns True iff:
        cassette.major == current.major
        AND cassette.minor <= current.minor

    This permits:
        - Same version
        - Cassette older minor than installed (forward compatibility)

    Refuses:
        - Different major version (schema may have changed)
        - Cassette newer minor than installed (CC was downgraded)
    """
    if cassette.major != current.major:
        return False
    if cassette.minor > current.minor:
        return False
    return True


def assert_cassette_compatible(
    cassette_version_str: str,
    *,
    cassette_path: Optional[str] = None,
    force: bool = False,
) -> None:
    """Raise CCVersionIncompatibleError if the cassette is not compatible.

    Args:
        cassette_version_str: The CC version recorded in the cassette
            (typically read from the sidecar .json or the inline ccipc_meta).
        cassette_path: Optional path for inclusion in error messages.
        force: If True, only emit a warning to stderr; do not raise. This is
            the --force-cross-version-fork escape hatch.

    Raises:
        CCVersionIncompatibleError: When versions don't satisfy is_compatible()
            and force is False.
    """
    cassette = parse_cc_version(cassette_version_str)
    current = get_installed_cc_version()

    # If we can't detect the current CC, we can't enforce compat. Conservative
    # behavior: don't block. The hydrate step will fail loudly if CC is missing
    # for a different reason.
    if current is None:
        return

    if cassette is None:
        # Cassette doesn't have a version recorded. Treat as legacy -- proceed
        # silently. Only Phase 1 cassettes will hit this path.
        return

    if is_compatible(cassette, current):
        return

    if force:
        import sys
        print(
            f"Warning: cassette CC {cassette} vs current CC {current} -- "
            f"--force-cross-version-fork was passed, proceeding anyway.",
            file=sys.stderr,
        )
        return

    raise CCVersionIncompatibleError(
        cassette_cc_version=str(cassette),
        current_cc_version=str(current),
        cassette_path=cassette_path,
    )

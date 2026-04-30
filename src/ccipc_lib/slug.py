"""sanitizePath -- Python port of Claude Code's project-directory slug fn.

Verified against C:\\code-ext\\claude-code\\utils\\sessionStoragePortable.ts:311-319
and C:\\code-ext\\claude-code\\utils\\hash.ts:7-13.

CC's algorithm:

    function sanitizePath(name) {
        const sanitized = name.replace(/[^a-zA-Z0-9]/g, '-')
        if (sanitized.length <= MAX_SANITIZED_LENGTH) return sanitized
        const hash = typeof Bun !== 'undefined'
            ? Bun.hash(name).toString(36)
            : Math.abs(djb2Hash(name)).toString(36)
        return sanitized.slice(0, MAX_SANITIZED_LENGTH) + '-' + hash
    }

CC's djb2Hash (NOT the classic Bernstein variant -- uses *31 starting at 0):

    function djb2Hash(str) {
        let hash = 0
        for (let i = 0; i < str.length; i++) {
            hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
        }
        return hash  // signed 32-bit int (range -2^31 .. 2^31-1)
    }

ccipc uses the Node-fallback path (djb2Hash) since Python doesn't have
Bun. CC's findProjectDir (sessionStoragePortable.ts:347-380) tolerates
djb2-vs-wyhash mismatch via prefix-matching, so this is safe even when
the user's CC is using Bun.hash for the same path.

Inputs are first canonicalized: realpath + NFC normalization, mirroring
canonicalizePath() in the same TS file.
"""

from __future__ import annotations

import os
import unicodedata

from ccipc_lib.cc_constants import (
    MAX_SANITIZED_LENGTH,
    SANITIZE_PATH_PATTERN,
    SANITIZE_PATH_REPLACEMENT,
)

import re

_SANITIZE_RE = re.compile(SANITIZE_PATH_PATTERN)

# Constants for signed-32-bit integer arithmetic (matching JS `| 0` semantics).
_INT32_MAX = 0x7FFFFFFF
_INT32_OVERFLOW = 0x100000000  # 2^32


def djb2_hash(s: str) -> int:
    """Port of CC's djb2Hash. Returns a SIGNED 32-bit integer.

    NB: CC's variant is unusual:
      - Starts at hash = 0 (classic djb2 starts at 5381)
      - Uses (hash << 5) - hash = hash * 31 (classic djb2 uses *33)
      - Coerces with `| 0` after each step to truncate to int32

    Equivalent algorithm in idiomatic Python.
    """
    hash_val = 0
    for c in s:
        # ((hash << 5) - hash + charCode) | 0
        hash_val = ((hash_val << 5) - hash_val + ord(c)) & 0xFFFFFFFF
        # JS `| 0` coerces to signed int32. In Python we manually wrap.
        if hash_val > _INT32_MAX:
            hash_val -= _INT32_OVERFLOW
    return hash_val


def _to_base36_abs(n: int) -> str:
    """Math.abs(n).toString(36) in Python, matching JS output exactly.

    JS toString(36) uses lowercase digits 0-9a-z. Python's standard library
    has no built-in for this, so we roll one.
    """
    n = abs(n)
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result: list[str] = []
    while n > 0:
        result.append(digits[n % 36])
        n //= 36
    return "".join(reversed(result))


def sanitize_path(name: str) -> str:
    """Sanitize a string for use as a filesystem-safe directory name.

    Mirrors CC's sanitizePath. Replaces non-alphanumeric chars with '-',
    and for inputs whose sanitized form is longer than MAX_SANITIZED_LENGTH,
    truncates and appends a djb2-base36 hash suffix.

    Args:
        name: Path or arbitrary string. Should be the output of canonicalize_path()
            for path-like inputs.

    Returns:
        Sanitized name. Always <= MAX_SANITIZED_LENGTH + 1 + len(hash).
    """
    sanitized = _SANITIZE_RE.sub(SANITIZE_PATH_REPLACEMENT, name)
    if len(sanitized) <= MAX_SANITIZED_LENGTH:
        return sanitized
    hash_suffix = _to_base36_abs(djb2_hash(name))
    return sanitized[:MAX_SANITIZED_LENGTH] + "-" + hash_suffix


def canonicalize_path(path: str) -> str:
    """Resolve a directory path to its canonical form.

    Mirrors CC's canonicalizePath(): realpath + NFC normalization. If realpath
    fails (path doesn't exist), falls back to NFC-only.

    Args:
        path: Path to canonicalize.

    Returns:
        Canonical path string. Use this as the input to sanitize_path() when
        deriving a slug from a project directory.
    """
    try:
        resolved = os.path.realpath(path)
    except OSError:
        resolved = path
    return unicodedata.normalize("NFC", resolved)


def slug_from_cwd(cwd: str) -> str:
    """Convenience: canonicalize then sanitize. The full CC slug pipeline.

    Use this when computing the project-dir name for ~/.claude/projects/
    from a working directory.
    """
    return sanitize_path(canonicalize_path(cwd))

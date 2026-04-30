"""ccipc configuration: TOML config at ~/.claude/ccipc/config.toml.

Per Round 4 decisions:
- Co-locates with CC under ~/.claude/ccipc/ rather than XDG ~/.config/.
- Includes a config_version key so future migrations are a one-line change.
- First-use is interactive: cost-estimate (and hydrate) prompt for the plan
  if the config doesn't exist. Non-TTY callers must pre-populate the file
  or pass --plan on the command line.

Config schema v1:

    config_version = 1
    plan = "max5"  # or "max20" | "api" | "1m"
    default_headroom_tokens = 25000
    default_model = "claude-sonnet-4-5"
    default_pricing_basis = "input_only"

The migration framework is intentionally minimal but established. When v2
ships, add an entry to CONFIG_MIGRATIONS that takes a v1 dict and returns
a v2 dict; load_config() walks the chain.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Optional

# tomllib is stdlib in 3.11+; tomli is the backport for 3.10.
try:
    import tomllib  # type: ignore[import]
except ImportError:  # pragma: no cover -- 3.10 path
    import tomli as tomllib  # type: ignore[import]

from ccipc_lib.cc_constants import (
    DEFAULT_MODEL,
    PLAN_DEFAULT_HEADROOM_TOKENS,
    VALID_PLANS,
)
from ccipc_lib.errors import ConfigError


CURRENT_CONFIG_VERSION = 1


def get_config_dir() -> Path:
    """Return ~/.claude/ccipc/, creating it lazily if needed.

    Override via CCIPC_CONFIG_DIR env var (used in tests).
    """
    env = os.environ.get("CCIPC_CONFIG_DIR")
    if env:
        return Path(env)
    home = Path.home()
    return home / ".claude" / "ccipc"


def get_config_path() -> Path:
    return get_config_dir() / "config.toml"


# Migration chain: each entry takes a config-dict at version K and returns
# a config-dict at version K+1. Add new entries when bumping CURRENT_CONFIG_VERSION.
#
# Example future entry:
#   2: lambda c: {**c, "new_field": "default", "config_version": 2},
CONFIG_MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    # No migrations yet -- v1 is current.
}


def _apply_migrations(raw: dict) -> dict:
    """Walk the migration chain until the config is at CURRENT_CONFIG_VERSION."""
    version = raw.get("config_version", 1)
    while version < CURRENT_CONFIG_VERSION:
        migrate = CONFIG_MIGRATIONS.get(version + 1)
        if migrate is None:
            raise ConfigError(
                f"No migration defined from config_version {version} to {version + 1}",
                config_path=str(get_config_path()),
            )
        raw = migrate(raw)
        version = raw.get("config_version", version + 1)
    return raw


def load_config(*, required: bool = False) -> Optional[dict]:
    """Load the user's ccipc config. Returns None if the file doesn't exist.

    Args:
        required: If True, raise ConfigError when the file is missing.

    Returns:
        The config dict, or None if the file doesn't exist and required=False.

    Raises:
        ConfigError: If required=True and the file is missing, or if the
            file exists but is malformed.
    """
    path = get_config_path()
    if not path.exists():
        if required:
            raise ConfigError(
                "config file not found",
                config_path=str(path),
            )
        return None
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(
            f"failed to parse config: {e}",
            config_path=str(path),
        ) from e
    raw = _apply_migrations(raw)
    _validate_config(raw)
    return raw


def _validate_config(raw: dict) -> None:
    """Validate config invariants. Raises ConfigError on any issue."""
    plan = raw.get("plan")
    if plan is None:
        raise ConfigError("missing required key: plan", config_path=str(get_config_path()))
    if plan not in VALID_PLANS:
        raise ConfigError(
            f"plan must be one of {VALID_PLANS}, got {plan!r}",
            config_path=str(get_config_path()),
        )


def save_config(config: dict) -> None:
    """Write the config to disk. Creates parent directory if needed.

    For Phase 1 we use a hand-rolled TOML writer since `tomllib` is read-only
    and `tomli_w` is an additional dep. The schema is small and flat enough
    that a few lines of formatting suffice.
    """
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Order keys deterministically so config diffs are clean.
    keys_order = [
        "config_version",
        "plan",
        "default_headroom_tokens",
        "default_model",
        "default_pricing_basis",
    ]
    lines: list[str] = []
    for k in keys_order:
        if k not in config:
            continue
        v = config[k]
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        else:
            lines.append(f"{k} = {v}")
    # Stable trailing newline.
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def make_default_config(plan: str) -> dict:
    """Build a config dict with v1 defaults for the chosen plan."""
    if plan not in VALID_PLANS:
        raise ConfigError(f"invalid plan {plan!r}; must be one of {VALID_PLANS}")
    return {
        "config_version": CURRENT_CONFIG_VERSION,
        "plan": plan,
        "default_headroom_tokens": PLAN_DEFAULT_HEADROOM_TOKENS[plan],
        "default_model": DEFAULT_MODEL,
        "default_pricing_basis": "input_only",
    }


def prompt_for_plan_and_save(*, stream=sys.stderr, in_stream=sys.stdin) -> dict:
    """Interactive first-use prompt. Asks for the plan, writes config, returns it.

    Used by cost-estimate and hydrate when load_config() returns None and
    we're connected to a TTY. For non-TTY callers, error out with a useful
    message instead of hanging.
    """
    if not in_stream.isatty():
        raise ConfigError(
            "no config and not running interactively",
            config_path=str(get_config_path()),
        )

    print("First-time ccipc setup.", file=stream)
    print("", file=stream)
    print("Which Claude Code plan are you on?", file=stream)
    print("  max5    - Max 5x ($100/mo, ~88K tokens / 5h window)", file=stream)
    print("  max20   - Max 20x ($200/mo, ~220K tokens / 5h window)", file=stream)
    print("  api     - Pay-per-token API (no 5h window)", file=stream)
    print("  1m      - 1M-context API tier", file=stream)
    print("", file=stream)
    while True:
        print("Plan [max5/max20/api/1m]: ", end="", file=stream, flush=True)
        ans = in_stream.readline().strip().lower()
        if ans in VALID_PLANS:
            break
        print(f"  invalid: must be one of {VALID_PLANS}", file=stream)

    config = make_default_config(ans)
    save_config(config)
    print(f"Saved {get_config_path()}.", file=stream)
    print("Pass --plan on any command to override per-invocation.", file=stream)
    return config


def get_or_prompt_config(*, plan_override: Optional[str] = None) -> dict:
    """Common entry point used by tools.

    Resolution order:
        1. --plan flag (plan_override) -- one-off, doesn't write to config.
        2. Existing ~/.claude/ccipc/config.toml.
        3. Interactive prompt + save (TTY only).
        4. ConfigError if non-interactive and no config exists.
    """
    if plan_override is not None:
        if plan_override not in VALID_PLANS:
            raise ConfigError(
                f"--plan must be one of {VALID_PLANS}, got {plan_override!r}"
            )
        return make_default_config(plan_override)

    config = load_config()
    if config is not None:
        return config

    return prompt_for_plan_and_save()

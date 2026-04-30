"""Unit tests for ccipc_lib.config."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from ccipc_lib.config import (  # noqa: E402
    CURRENT_CONFIG_VERSION,
    get_config_dir,
    get_config_path,
    get_or_prompt_config,
    load_config,
    make_default_config,
    prompt_for_plan_and_save,
    save_config,
)
from ccipc_lib.cc_constants import PLAN_DEFAULT_HEADROOM_TOKENS, VALID_PLANS  # noqa: E402
from ccipc_lib.errors import ConfigError  # noqa: E402


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point ccipc config at a temp dir for the test duration."""
    monkeypatch.setenv("CCIPC_CONFIG_DIR", str(tmp_path))
    return tmp_path


class TestMakeDefault:
    def test_max5_defaults(self):
        c = make_default_config("max5")
        assert c["plan"] == "max5"
        assert c["config_version"] == CURRENT_CONFIG_VERSION
        assert c["default_headroom_tokens"] == PLAN_DEFAULT_HEADROOM_TOKENS["max5"]

    def test_invalid_plan_raises(self):
        with pytest.raises(ConfigError):
            make_default_config("not-a-plan")


class TestSaveLoad:
    def test_save_and_load_roundtrip(self, isolated_config):
        c = make_default_config("api")
        save_config(c)
        loaded = load_config()
        assert loaded == c

    def test_load_missing_returns_none(self, isolated_config):
        assert load_config() is None

    def test_load_missing_required_raises(self, isolated_config):
        with pytest.raises(ConfigError):
            load_config(required=True)

    def test_load_malformed_raises(self, isolated_config):
        get_config_path().parent.mkdir(parents=True, exist_ok=True)
        get_config_path().write_text("not [valid toml at all===", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config()

    def test_load_invalid_plan_raises(self, isolated_config):
        get_config_path().parent.mkdir(parents=True, exist_ok=True)
        get_config_path().write_text(
            'config_version = 1\nplan = "bogus"\n', encoding="utf-8",
        )
        with pytest.raises(ConfigError):
            load_config()


class TestGetOrPromptConfig:
    def test_explicit_plan_override_wins(self, isolated_config):
        c = get_or_prompt_config(plan_override="max20")
        assert c["plan"] == "max20"
        # plan-override path does NOT write to disk.
        assert load_config() is None

    def test_invalid_plan_override_raises(self, isolated_config):
        with pytest.raises(ConfigError):
            get_or_prompt_config(plan_override="invalid-x")

    def test_loads_existing_config(self, isolated_config):
        c = make_default_config("max5")
        save_config(c)
        loaded = get_or_prompt_config()
        assert loaded["plan"] == "max5"

    def test_non_tty_no_config_raises(self, isolated_config, monkeypatch):
        # No config + non-TTY stdin -> error.
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        with pytest.raises(ConfigError):
            get_or_prompt_config()


class TestPromptForPlanAndSave:
    def test_prompts_until_valid(self, isolated_config, monkeypatch):
        # Simulate interactive input: "bogus\nmax5\n" -- first invalid, then valid.
        fake_stdin = io.StringIO("bogus\nmax5\n")
        fake_stdin.isatty = lambda: True  # type: ignore[method-assign]
        fake_stderr = io.StringIO()
        cfg = prompt_for_plan_and_save(stream=fake_stderr, in_stream=fake_stdin)
        assert cfg["plan"] == "max5"
        # The config was written to disk.
        loaded = load_config()
        assert loaded == cfg

    def test_non_tty_raises_immediately(self, isolated_config):
        fake_stdin = io.StringIO("max5\n")
        fake_stdin.isatty = lambda: False  # type: ignore[method-assign]
        with pytest.raises(ConfigError):
            prompt_for_plan_and_save(stream=io.StringIO(), in_stream=fake_stdin)

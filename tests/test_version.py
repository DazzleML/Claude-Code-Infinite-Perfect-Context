"""Tests for the canonical version module (src/ccipc_lib/_version.py)."""

from ccipc_lib._version import (
    MAJOR, MINOR, PATCH, PHASE, PROJECT_PHASE,
    get_version, get_base_version, get_display_version, get_pip_version,
    __app_name__,
)


def test_app_name():
    assert __app_name__ == "Claude-Code-Infinite-Perfect-Context"


def test_version_components():
    assert isinstance(MAJOR, int)
    assert isinstance(MINOR, int)
    assert isinstance(PATCH, int)


def test_phase_valid():
    """PHASE is empty string (stable) or a string like 'alpha', 'beta', 'rc1'."""
    assert isinstance(PHASE, str)


def test_get_version_returns_string():
    v = get_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_base_version_format():
    base = get_base_version()
    assert base.startswith(f"{MAJOR}.{MINOR}.{PATCH}")


def test_display_version_includes_project_phase():
    display = get_display_version()
    if PROJECT_PHASE and PROJECT_PHASE != "stable":
        assert PROJECT_PHASE.upper() in display
    else:
        assert display == get_base_version()


def test_pip_version_pep440():
    pip_v = get_pip_version()
    assert "-" not in pip_v
    if PHASE:
        assert any(c.isalpha() for c in pip_v.split(".")[-1])
    else:
        assert all(c.isdigit() or c == "." for c in pip_v)


def test_ccipc_re_export():
    """The ccipc package should re-export the same version data as ccipc_lib."""
    from ccipc._version import (
        __version__ as ccipc_version,
        __app_name__ as ccipc_app_name,
        PIP_VERSION as ccipc_pip,
    )
    from ccipc_lib._version import (
        __version__ as ccipc_lib_version,
        __app_name__ as ccipc_lib_app_name,
        PIP_VERSION as ccipc_lib_pip,
    )
    assert ccipc_version == ccipc_lib_version
    assert ccipc_app_name == ccipc_lib_app_name
    assert ccipc_pip == ccipc_lib_pip

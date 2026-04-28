# Contributing to Claude-Code-Infinite-Perfect-Context

Thank you for considering contributing to Claude-Code-Infinite-Perfect-Context!

## Development Setup

### Prerequisites

- **Python 3.10+**
- **Git**

### Clone and Install

```bash
git clone https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context.git
cd Claude-Code-Infinite-Perfect-Context
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# or: .venv\Scripts\activate     # Windows
pip install -e ".[dev]"
```

### Run Tests

```bash
python -m pytest tests/ -v
```

## Project Structure

```
Claude_Code_Infinite_Perfect_Context/
  __init__.py         # Package initialization
  __main__.py         # CLI entry (python -m Claude_Code_Infinite_Perfect_Context)
  _version.py         # Version (PEP 440)
tests/
  conftest.py         # Shared fixtures
  test_*.py           # Test files
  one-offs/           # Quick checks, proof-of-concept scripts
scripts/
  repokit-common/     # Shared tools (git submodule)
```

## Key Design Principles

1. **Tests are important** -- write tests for new features
2. **One-offs graduate** -- quick tests in `tests/one-offs/` can be promoted to proper tests
3. **Cross-platform** -- works on Windows, Linux, macOS
4. **Clean commits** -- use conventional commit format

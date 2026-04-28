# Claude-Code-Infinite-Perfect-Context

A new project created from git-repokit-template

## Installation

```bash
pip install Claude_Code_Infinite_Perfect_Context
```

### From Source

```bash
git clone https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context.git
cd Claude-Code-Infinite-Perfect-Context
pip install -e ".[dev]"
```

## Usage

```bash
Claude-Code-Infinite-Perfect-Context --help
```

## Development

```bash
# Clone and install
git clone https://github.com/DazzleML/Claude-Code-Infinite-Perfect-Context.git
cd Claude-Code-Infinite-Perfect-Context
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Install git hooks (if using repokit-common submodule)
bash scripts/repokit-common/install-hooks.sh
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) for details.


#!/bin/bash
# The one dev environment setup for goldlabel. Claude Code runs it at every session start (the
# SessionStart hook in .claude/settings.json), locally and in the cloud; people can run it by hand.
# Safe to rerun: it does only what is missing. Its stdout reaches Claude, so tools write to stderr.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}"

if ! command -v uv >/dev/null; then
  python3 -m pip install --user uv >&2
  export PATH="$HOME/.local/bin:$PATH"
fi

# The same install as CI, rerun only when a file that decides it changed since it last succeeded.
hashes=.venv/.dev-setup.sha256
if ! sha256sum --check --status "$hashes" 2>/dev/null; then
  rm -f "$hashes"
  uv sync --all-extras >&2
  sha256sum scripts/dev-setup.sh pyproject.toml uv.lock > "$hashes"
fi

# Commits must go through ruff, ty and pytest, as CI does.
if [ ! -f "$(git rev-parse --git-path hooks/pre-commit)" ]; then
  uv run pre-commit install >&2
fi

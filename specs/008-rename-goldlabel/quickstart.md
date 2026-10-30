# Quickstart: verifying the rename

Run from the repository root after implementation; every step must pass.

1. **Checks**: `uv sync --all-extras`, then `uv run ruff check`, `uv run ruff format --check`,
   `uv run ty check`, `uv run pytest`.
2. **Leftover name** (SC-002): `uv run pytest tests/test_no_old_name.py -n0`. It fails on the old name or alias in any
   tracked file or file name outside `specs/`.
3. **Wheel** (SC-001, SC-005): `uv build`, then
   `unzip -l dist/goldlabel-0.1.0-py3-none-any.whl | grep -E 'goldlabel/(web/|gold_rule.md)'`
   shows the web assets and the rule text; `unzip -l` shows no `hunches/` path.
4. **Clean install** (SC-001), in a throwaway directory:
   `uv venv && uv pip install dist/goldlabel-0.1.0-py3-none-any.whl`, then
   `python -c "import goldlabel as gl; print(gl.__version__)"` prints `0.1.0`, and
   `python -c "import hunches"` raises `ModuleNotFoundError`.
5. **Gold rule** (SC-003): `uv run pytest tests/test_gold_rule.py tests/test_skills.py tests/test_docs.py -n0`.
6. **Stamp** (SC-004): `uv run pytest tests/test_gold.py tests/test_label_server.py -n0` (the page stamps
   `goldlabel-ui`; the summary counts it under that name).
7. **Defaults**: with `GOLDLABEL_DIR` unset, `gl.settings.root` is `.goldlabel`
   (`tests/test_settings.py`).

Needs a human (report, never fake): reinstall the plugin as `goldlabel` in Claude Code, Codex,
Copilot CLI and Kiro and run the gold-rule refusal trial; check the README's unverified install
commands; look at the labelling page in a browser; rename the GitHub repository.

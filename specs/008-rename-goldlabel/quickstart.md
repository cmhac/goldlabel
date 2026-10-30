# Quickstart: verifying the rename

Run from the repository root after implementation; every step must pass.

1. **Checks**: `uv sync --all-extras`, then `uv run ruff check`, `uv run ruff format --check`,
   `uv run ty check`, `uv run pytest`.
2. **Leftover name** (SC-002): `uv run pytest tests/test_no_old_name.py -n0`. Also by hand:
   `git ls-files | xargs grep -Iil hunches` lists only the allowlisted files.
3. **Wheel** (SC-001, SC-005): `uv build`, then
   `unzip -l dist/goldlabel-0.1.0-py3-none-any.whl | grep -E 'goldlabel/(web/|gold_rule.md)'`
   shows the web assets and the rule text; `unzip -l` shows no `hunches/` path.
4. **Clean install** (SC-001), in a throwaway directory:
   `uv venv && uv pip install dist/goldlabel-0.1.0-py3-none-any.whl`, then
   `python -c "import goldlabel as gl; print(gl.__version__)"` prints `0.1.0`, and
   `python -c "import hunches"` raises `ModuleNotFoundError`.
5. **Gold rule** (SC-003): `uv run pytest tests/test_gold_rule.py tests/test_skills.py tests/test_docs.py -n0`.
6. **Legacy labels** (SC-004): `uv run pytest tests/test_gold.py -n0 -k legacy` (the hand-built
   `hunches-ui` fixture is 100% labelled through the page, file bytes unchanged).
7. **Migration** (US3.4): with `GOLDLABEL_DIR` unset and a `.hunches/` present in a temp
   directory, `gl.settings.root` is `.goldlabel`.

Needs a human (report, never fake): reinstall the plugin as `goldlabel` in Claude Code, Codex,
Copilot CLI and Kiro and run the gold-rule refusal trial; check the README's unverified install
commands; look at the labelling page in a browser; rename the GitHub repository.

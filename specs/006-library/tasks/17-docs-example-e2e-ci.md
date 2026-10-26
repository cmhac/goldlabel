# 17 — Docs, example, end-to-end test, CI, superseded markers, size report

Spec: FR-25, SC-1, SC-2, SC-5, "What is kept, changed, removed".

**Do**
- Rewrite `README.md` around the notebook flow (any tabular display in the README and example uses polars via `.to_polars()`; mention `.to_pandas()` exists): what it is; install (`pip install hunches`, extras `s3`, `pg`, `rds`, `local`); the example chain from the spec; where files go and how to move them; API keys (environment variables or a `.env` the user loads themselves; the library never reads or writes a keyring); the labelling page; reusing a classifier (bundle and shared module); the evaluation log; per-harness install commands (Claude Code, Codex, Copilot CLI, Kiro, any agent) copied from the spec; the agent instruction block from `docs/agent-instructions.md`; a plain statement that agents may not write gold labels.
- Rewrite `AGENTS.md` (`CLAUDE.md` stays a symlink): current state (006 implemented; what a human still must do), source-of-truth order (add 006 first), principles as amended, stack (no Textual, keyring, platformdirs, dotenv), commands (no `-m "not ui"`), layout of the new modules, testing notes, the gold rule in full near the top.
- Mark specs 001–005 `Superseded by 006 for everything user-facing (the TUI is removed)` in each spec's header line, leaving the text unchanged.
- Replace `examples/sample/.hunches/config.toml` and the old walkthrough with `examples/sample/walkthrough.ipynb` (no outputs) over the existing tiny local corpus, built once with `nbformat` from a scratch script that is not committed, plus `examples/sample/walkthrough.py` in `# %%` cell format with the same cells. It must not contain gold labels; its labelling cell calls `hn.label`.
- Rewrite `tests/test_e2e.py` (SC-1): the README chain end to end with a tiny hand-built corpus, a fake embedder, `FunctionModel` for the classifier, and a **simulated human** that labels over the HTTP API of task 13 in a background thread (this is a test of the pipeline, not an agent writing labels; keep that distinction in a comment). Assert: counts of `FunctionModel` calls per step (search none, first `evaluate` one per dev item, identical re-evaluate zero, changed prompt one per item), a `max_cost` refusal, a bundle `save`/`load` into a "pipeline" script that classifies new items, the evaluation log lines, and zero real network (the `no_real_models` guard).
- CI (`.github/workflows/ci.yml`): keep the `check` job unchanged in effect; keep the optional `pgvector` job (its test file was ported in task 05). Confirm no job references the TUI or the `ui` marker.
- Size report (SC-5): rerun the task-01 `wc -l` command and put before/after totals and the percentage in the task report and in the spec's "Success criteria" as a note.

**Tests**: the rewritten e2e test; a test that every fenced `python` block in the README only uses public `hunches` names; `uv run pytest` whole suite.

**Needs a human** (report, don't fake): run the example notebook in real Jupyter and in one other notebook environment (marimo or Colab) with real keys; the manual checks listed in the README of this task directory.

**Not in this task**: anything else. After this task the branch is ready for Chris's review; do not open a PR.

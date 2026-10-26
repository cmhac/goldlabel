# Tasks for 006 — Library, not TUI

Read `../spec.md` first (the source of truth), then your task file. If a task file and the spec disagree, flag it instead of guessing; if the spec is wrong or incomplete, say so and fix it in the same change. A task does only what its file says: later tasks own later behaviour. **Never implement beyond your task.**

## Rules for every task

- Repo rules in `/home/user/hunches/AGENTS.md` (`CLAUDE.md` is a symlink to it) apply, as amended by the spec's "Principles": minimal implementation (a plain `if`, no base class, registry or plugin system), no real LLM, AWS, database, keyring or browser in the default test run, check every Pydantic AI, pydantic-ai `Embedder`, psycopg, boto3 and standard-library API against the installed version and the current docs before using it (do not code from memory), unknown cost is `?`, never `$0`.
- **The gold rule is never relaxed.** No code path other than the labelling server and `Gold.import_rows` writes a gold label. Tests may build gold files by hand as fixtures; they never add a helper to the library that sets labels.
- **Red/green TDD, shown in the work.** Write the failing tests first and run them to see them fail for the right reason (not an import error you could have avoided); then implement until they pass. Report, per behaviour, the failing run (command and failure message) and the passing run. Expected values are hand-written in the tests, never derived by running the code under test. (The one exception is task 01, which records what the pre-006 code does so later tasks can prove they are compatible.)
- Tests use `tmp_path`, `monkeypatch.chdir`/`monkeypatch.setenv`, pydantic-ai `TestModel`/`FunctionModel`, the fake `psycopg` and stubbed `boto3` already in `tests/`, and tiny hand-built vectors. `tests/conftest.py`'s `no_real_models` guard stays.
- `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest` all pass before the commit. Report their actual output summaries.
- One commit per task on branch `claude/inspiring-babbage-qs4hzm`; commit message `006/NN: ...`; push the branch; do not open a PR.
- Update or delete existing tests the task breaks, in the same commit. Old module names appear in later tasks' "Do" lists only where they still exist at that point.
- Final report: what changed, files touched, red/green evidence, check outputs, deviations from the spec, anything only a human can do. Anything the spec marks "verify in the task" must be verified against the docs and the result written into the spec in the same commit.

## Order

| # | Task | Depends on |
|---|------|-----------|
| 01 | Record pre-006 behaviour as fixtures; baseline size | — |
| 02 | Remove the TUI completely | 01 |
| 03 | Settings, locations and the sync/async runner | 02 |
| 04 | Cost, cache and ledger take an explicit cache directory | 03 |
| 05 | Corpus classes and vector search without `Config` | 02 |
| 06 | `Taxonomy`, seeds, `Candidates` and `search()` | 04, 05 |
| 07 | `Classifier`, `Predictions`, `Estimate` | 04, 06 |
| 08 | `Gold`, `GoldSet`, `draw`, `import_rows` | 06 |
| 09 | `evaluate`, `Evaluation`, the evaluation log, `band_sample` | 07, 08 |
| 10 | Classifier bundles: `save` and `load` | 09 |
| 11 | Finish the removal: `files.py`, `system.py`, `keys.py`, `models.py`, dependencies, public API | 10 |
| 12 | Notebook displays (`_repr_html_`) and `to_pandas` | 11 |
| 13 | Labelling server (no page yet) | 11 |
| 14 | Labelling page, Tailwind CSS, `hn.label` | 13 |
| 15 | The gold rule: canonical text and run-time placement | 14, 12 |
| 16 | Skills, references, instruction block, steering file, plugin manifests | 15 |
| 17 | Docs, example, end-to-end test, CI, superseded markers, size report | all |

Run strictly in order, one at a time. Tasks 03 and 05 only need 02 and may be swapped.

Needs a human (agents report these and stop; they never fake them): installing and exercising the plugin in Claude Code, Codex, Copilot CLI and Kiro; the gold-rule refusal trial in each; looking at the labelling page in a real browser in light and dark and at phone width; running the example in real Jupyter and one other notebook (marimo or Colab); a real pgvector/RDS/S3 corpus and API keys (everything 005 listed).

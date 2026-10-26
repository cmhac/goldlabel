# AGENTS.md

(`CLAUDE.md` is a symlink to this file: keep it one.)

## The gold rule (read this first)

**Hard rule of the hunches library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the hunches labelling page (`hunches.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

Nothing in this repository may add a way to set a gold label. Only the labelling server (`hunches._label`) and `Gold.import_rows` write one, and tests build gold files by hand as fixtures (the end-to-end test's simulated human labels over the server's HTTP API, which tests the pipeline and is not an agent writing labels). Do not reword the rule; `src/hunches/gold_rule.md` is canonical and `tests/test_gold_rule.py`, `tests/test_skills.py` and `tests/test_docs.py` fail when a copy drifts, printing the text to paste.

## What this repo is

`hunches` is a Python library for content analysis over an already-embedded corpus: seed phrases -> semantic search -> candidates -> an LLM classifier validated against a hand-labelled gold set -> classified output. You build it step by step in a Jupyter notebook or a `# %%` script by chaining function calls whose results display themselves; the labelling page (`hn.label`) is a local web page. There is no application, no console script and no stored status. The repository is also an agent plugin (`skills/hunches/`, manifests) that teaches agents the idioms and the gold rule. Python package `hunches`, `import hunches as hn`.

## Current state

001-005 (the original Textual TUI, projects, history, pgvector backend) are history; **006 is implemented** (tasks 01-17, `specs/006-library/`): the TUI, projects, system settings, stage tracking, history and the `hunches` console script are gone, and the search, classifier, metrics, cost and pgvector logic they used is the library. The branch is ready for Chris's review. What a human still has to do (agents report these and stop, never fake them):

- Install the plugin in Claude Code, Codex, Copilot CLI and Kiro and run the gold-rule refusal trial in each (SC-6). Some install commands in the README are marked unverified (the Codex `plugin add` form, Copilot's `NAME@MARKETPLACE` form, `npx skills add ... -a kiro-cli`); the trial finds the real ones and records them in the spec's task 16 note.
- Look at the labelling page in a real browser: light, dark and phone width. (The page was screenshotted once with an ad-hoc Chromium/Playwright that is **not** a repo dependency and must not become one; the tests check the served page and CSS over HTTP only.)
- Run `examples/sample/walkthrough.ipynb` in real Jupyter and in one other notebook (marimo or Colab) with a real key.
- Everything 005 listed: a real pgvector, RDS/Aurora IAM, S3 Vectors, tables larger than memory (`specs/005-pgvector/manual-checklist.md`), API keys.
- Decide on a `LICENSE` file and a plugin icon (the manifests carry no `license`; `claude plugin validate .` advises both). Tags, releases and PyPI trusted publishing are Chris's.

## Source of truth (read in this order; the first wins)

1. `specs/006-library/spec.md`, with every "Implemented in task NN" and "Verified" note: they record the real API and what was and was not verified. Then your task file in `specs/006-library/tasks/` (`README.md` has the order and rules).
2. For kept behaviour only, the 001-005 sections named in 006's "What is kept": `specs/005-pgvector/spec.md` (its "Verified in task NN" and "Clarifications" win over its draft text) and `specs/005-pgvector/deltas/` in number order, then `004`, `003`, `002`, `001`. Everything user-facing in 001-005 is superseded (each spec's header says so).

**Before starting any work: read the spec, then your task file.** If a task file and the spec disagree, flag it instead of guessing. If the spec is wrong or incomplete, say so and update it in the same change.

## Principles (non-negotiable)

- Absolute minimal implementation. No abstraction, base class, registry or plugin system unless the user explicitly asks. Where two behaviours must coexist (local vs S3 vs pgvector), use a plain `if` in one function.
- **The code is the pipeline.** No status, approval flags, stage list, history log or chat history; the notebook and plain files are the record. Nothing reads `config.toml`, the working directory's `.hunches/` or the OS keyring behind the caller's back: every object carries what it needs, and files go where the argument, then `hn.settings.root` (`HUNCHES_DIR`), then `.hunches/` say.
- The library never runs git, never loads a `.env`, never reads or writes a keyring. Keys and database URLs come from environment variables; never commit one.
- Every I/O function has an async and a sync form; the sync form works inside a notebook's running event loop (`_sync.run`).
- Result objects have a plain `__repr__` and a `_repr_html_` that escapes everything, sets no colour and says state in words (PASS/FAIL, `cost ?`, WARNING). Tables export `.to_polars()` and `.to_pandas()` together, never one alone; docs and examples use polars.
- Check every Pydantic AI, `Embedder`, psycopg, boto3 and standard-library API against the installed version and current docs before using it. Do not code from memory. Pydantic AI docs: https://pydantic.dev/docs/ai/ (`llms.txt` index).
- Never call a real LLM, AWS API, database, keyring or browser in tests: `TestModel`/`FunctionModel`, stubbed boto3, the fake `psycopg`, tiny hand-built vectors.
- Never show a cost of $0 when the price is unknown. Unknown is `?` with a warning, and `max_cost` refuses.
- Evaluations are logged (`evals.jsonl`, append-only); the test split is evaluated once, at the end.

## Stack

Python 3.12+, `uv`, `pydantic-ai-slim` (Agent, Embedder; anthropic and openai extras), `numpy`, `genai-prices`, `pyyaml`; optional extras `s3` (`boto3`), `pg` (`psycopg[binary]`), `rds` (`psycopg[binary]` + `boto3`), `local` (Sentence Transformers). Standard-library `http.server` for the labelling page, vanilla JavaScript, Tailwind CSS pre-built into `src/hunches/web/app.css` (see `web/README.md`). Dev group: `pytest`, `pytest-asyncio` (`asyncio_mode = "auto"`), `pytest-xdist`, `ruff`, `ty`, `pre-commit`, `polars`, `pandas` (the last two only for the export tests). **No** Textual, keyring, platformdirs, python-dotenv, nbformat or Playwright; a build or example script that needs one runs it with `uv run --with` and does not add it to the project.

## Commands

```
uv sync --all-extras
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest                  # everything, parallel via pytest-xdist
uv run pytest tests/test_x.py -n0   # one file, in-process (easier to debug)
uv build                       # wheel must contain hunches/web/* and hunches/gold_rule.md
```

Ruff, ty and pytest must pass before every commit (pre-commit enforces it). There is no `hunches` command. CI (`.github/workflows/ci.yml`) runs the four checks; its optional `pgvector` job runs `tests/test_pg_integration.py` against a real pgvector and is skipped locally unless `HUNCHES_TEST_PG_URL` is set.

## Layout

- `src/hunches/__init__.py` exports exactly the public names. **Package quirk:** `hunches.search`, `hunches.cost` and `hunches.settings` on the package are the *function*, the *function* and the *object*, not the submodules. Inside the package and in tests import by name (`from hunches.search import LocalCorpus`, `from hunches.cost import cache_key`, `from hunches.settings import settings, resolve`); a test that needs a whole module uses `importlib.import_module("hunches.cost")`. Importing `hunches` does no I/O and imports none of textual, keyring, platformdirs, dotenv, boto3, psycopg, polars or pandas.
- `search.py` (corpus classes `LocalCorpus`/`S3Corpus`/`PgCorpus`, `search_vectors`, all pgvector code: `search_pg_exact`, `index` mode, `PgCorpus.check`, the scrubber; read-only, `psycopg.sql.Identifier`), `candidates.py` (`Candidates`, `search`/`asearch`, `read_seeds`, bands), `taxonomy.py`, `classifier.py` (`Classifier`, `Predictions`, `Estimate`, `CostLimit`, `save`/`load`, cache), `evaluation.py` (`evaluate`, `Evaluation`, the log, `band_sample`), `metrics.py`, `cost.py` (ledger in the cache directory, prices via `genai-prices`), `gold.py` (`Gold`, `GoldSet`, `draw`, `import_rows`), `settings.py` (`settings.root`, `resolve`).
- Private helpers: `_sync.py` (sync wrapper over a running loop), `_html.py` and `_frame.py` (reprs and polars/pandas), `_label.py` (the labelling server and `label`), `_gold_rule.py` + `gold_rule.md` (the canonical rule, `GOLD_RULE_SHORT/FULL`, `GoldError`), `web/` (index.html, app.js, app.css, input.css).
- Agents: `skills/hunches/SKILL.md` and `references/{workflow,tuning,running,reuse}.md`, `docs/agent-instructions.md` (the block pasted in `README.md`), `.kiro/steering/hunches.md`, `.claude-plugin/{plugin,marketplace}.json`, root `plugin.json`.
- `examples/sample/` is the walkthrough (`walkthrough.ipynb`, no outputs, and `walkthrough.py`, the same cells) over a tiny local corpus; `tests/` mirrors the modules; `specs/` is history plus 006.

## Testing notes

- `tests/conftest.py` has autouse fixtures: `reset_settings` (root back to `.hunches`) and `no_real_models` (unusable keys; any un-stubbed model request fails the test). Use `tmp_path` and `monkeypatch.chdir`.
- "No model call" is proved by counting `FunctionModel` invocations: a first `evaluate` makes one per row, an identical one none, a changed prompt one per row. `tests/test_e2e.py` runs the README chain this way, with the labelling done by a simulated human over HTTP in a background thread.
- Metrics tests compare against hand-computed values written in the test; never derive an expected value by running the code under test.
- `tests/fixtures/pre006/` holds files written by the pre-006 code (cache, gold, candidates, ledger) so compatibility is checked against the real thing; the pgvector tests use a fake `psycopg`; `tests/test_pg_integration.py` needs `HUNCHES_TEST_PG_URL`.
- Drift tests: `test_skills.py` (every code block in the skill and references uses real names; the rule is verbatim), `test_docs.py` (README blocks use public names, the README block equals `docs/agent-instructions.md`, notebook == script).

## Conventions

- Match surrounding code style; comments only where the why is not obvious.
- One commit per task (`006/NN: ...`) on the branch you were assigned; do not open a PR unless asked.
- Don't tag, release or publish. The user pushes tags; PyPI uses trusted publishing (no token in secrets).

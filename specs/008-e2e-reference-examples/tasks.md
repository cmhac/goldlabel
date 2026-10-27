---

description: "Task list for the end-to-end reference examples"
---

# Tasks: End-to-end reference examples

**Input**: `specs/008-e2e-reference-examples/` (`spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/example-run.md`, `quickstart.md`)

**Prerequisites**: spec clarified, plan written, constitution v1.2.0. Environment: `uv sync --all-extras`, `podman` 4.x on the PATH. There is **no API key** in the agent sandbox: an agent verifies everything that does not call the model and reports the rest as human steps (never fakes it). Baseline before any task: `uv run pytest` passes (record the count in T001's report).

**Tests**: the examples are the end-to-end checks and are not unit-tested. Everything that can be checked offline is, red/green (constitution Principle IV): `tests/test_e2e_folder.py` (data agreement, folder completeness, public names, no `docker`) and the `cache_put` test. For an example, the evidence a task reports is: the real run (`RESULT:` line), one deliberately wrong expected value showing the failure message with the check name and both values, `podman ps -a --filter label=hunches-e2e` empty afterwards, and `git status --short` unchanged. Expected values are written by hand, never produced by running the code under test.

**Organization**: one task is one commit (`008/TNN: ...`) on branch `ccr-26b50054-jcevqw`. Before every commit run `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pytest`, all green, with the output summaries reported; never `--no-verify`. The suite must pass after every commit, so a move or removal is done in the same task as every caller of it. Tasks are sequential (no `[P]`): they share `e2e/common/` and `tests/test_e2e_folder.py`. Containers: `podman` only, never `docker` (constitution v1.1.0). Do not open a PR.

**Gold rule**: no task writes, edits, completes or infers a gold label. `e2e/common/gold.jsonl` and `GOLD.md` are made by Chris in the labelling page (human step H1) and are never touched by an agent. Before H1 exists, evaluation steps report `skipped` with a reason that says so.

## Format: `- [ ] TNN [Story] Description with file path`

Story labels map to `spec.md`: US1 table, US2 Postgres and pgvector, US3 S3, US4 walkthrough, US5 README and drift checks. No label: constitution, dependencies, shared data.

## Phase 1: Setup

- [X] T001 Amend the constitution (FR-016) with `/speckit-constitution`: Principle IV's rule against calling real services in tests applies to the default checks (`uv run pytest`, pre-commit, CI); opt-in end-to-end runs under `e2e/` may use isolated local containers (Podman) and the model provider with a key from the environment. MINOR bump to 1.3.0, Last Amended 2026-10-27. Change **nothing** in Principle I (diff must show it untouched) and keep the Principle IV red/green and hand-computed-value rules. Record Chris's approval by quoting his 2026-10-27 message: "constitution principle iv's no-real-database-or-api requirement does not count for these, as they are going to use podman local dev not real services. that requirement was intended to prevent having tests relying on real external services not isolated local dev emulators." Update the AGENTS.md "Principles" bullet that repeats the rule ("Never call a real LLM, AWS API, database, keyring or browser in tests") to say "default tests". Run `tests/test_docs.py` and `tests/test_skills.py` (drift tests). Files: `.specify/memory/constitution.md`, `AGENTS.md`.

- [X] T002 Plumbing, no behaviour change. (a) `uv add --dev nbclient ipykernel` (justified in plan "Complexity Tracking"; not `pyarrow`, not a runtime dependency or extra). (b) `uv lock --upgrade-package genai-prices`, then confirm with `uv run python -c` that `calc_price(Usage(input_tokens=1000, output_tokens=200), 'claude-haiku-5-5', provider_id='anthropic')` returns 0.0002 (hand-computed: 1000 x $0.10/M + 200 x $0.50/M = $0.0001 + $0.0001) and that the full suite still passes on the new lock. (c) Add `e2e/.cache/` to `.gitignore`. (d) `pyproject.toml`: add `"e2e/**" = ["B018"]` to `[tool.ruff.lint.per-file-ignores]` next to the existing `examples/**` line (T010 removes that one). Files: `pyproject.toml`, `uv.lock`, `.gitignore`.

- [X] T003 Make `cache_put` atomic in `src/hunches/cost.py`: write `<key>.json.tmp` with a per-process unique suffix, then `os.replace` onto `<key>.json` (the way `Gold._write` does it); remove the temp file if the write fails. Red first in `tests/test_cost.py`: (1) after `cache_put` the directory holds only `<key>.json` and `cache_get` returns the entry; (2) with `os.replace` patched to raise, no `<key>.json` exists (a reader never sees a half-written entry) and no `.tmp` is left behind. (Not `json.dumps` raising: it runs before any file is opened, so that case passes today and would not be red.) Leave `cost.json`'s read-modify-write alone (documented thread-only; research R5). Files: `src/hunches/cost.py`, `tests/test_cost.py`.

---

## Phase 2: Foundational (blocks every example)

**Purpose**: the one corpus and the shared helper every example reads. Chris must approve the corpus, taxonomy and prompt before he labels (human step H1); changing them afterwards makes gold rows stale.

- [X] T004 Common data, with its offline check. Create in `e2e/common/` (shapes from `data-model.md`; quoted rules: "`id` | string | unique, stable; the text is never edited after labelling"; "`text` | string | non-empty; at least one item each with `%`, `_` and `\`"; "`embedding` | list of 2 floats | unit length; both numbers from the Pythagorean table in research R3"):
  - `corpus.jsonl`: 60 workplace posts, about 20 each layoff / burnout / off-topic, with hard cases (rumoured redundancies, tiredness not caused by work, one mentioning both) and at least one item each containing `%`, `_` and a backslash. Ids like `p01`..`p60`. Embeddings only from (1,0), (0.96,0.28), (0.8,0.6), (0.6,0.8), (0.28,0.96), (0,1); layoff items near (1,0), burnout near (0,1).
  - `taxonomy.yaml` (`mode: single`, labels `layoff` and `burnout` with descriptions), `prompt.md` (the plain one-sentence prompt; the rumour rule is the walkthrough's second prompt, T010), `seeds.json` (two or three seed phrases mapped to (1,0) and (0,1)).
  - `expected.json` per the data-model table: `whole` (all ids in corpus order), `keywords` (at least: a two-term plain search with ranked ids plus `terms_matched`/`matches`; a regex using an inline flag such as `(?i)laid off|redundan`; one term each for `%`, `_` and a backslash; the same plain search under `limit=5`), `seeds` (per seed: ids at the floor 0.60 with similarity and band, `best_seed`), `score_floor` (0.70, a lower bound; Chris may change it). **Every number computed by hand** from the corpus text and vectors (cosine to an axis seed is the coordinate), written out in a short comment-free derivation in the task report, never obtained by calling the library.
  - `tests/test_e2e_folder.py` (new; red first, run it before the data exists to see the missing-file failures): 60 unique ids; non-empty texts; vectors length 2, unit length within 1e-9 and drawn from the allowed table; the three special characters each present; taxonomy loads with `hunches.Taxonomy`; every `expected.json` id is in the corpus; **expected similarities re-derived in the test from the vectors with plain arithmetic** (not by calling the library); gold checks: if `e2e/common/gold.jsonl` is missing, `pytest.skip("gold labels not made yet: Chris labels them, see e2e/README.md")`, otherwise each row's id and text equal a corpus item, each label is in the taxonomy plus `off_topic`, `labelled_by == "hunches-ui"`, and the failure names the offending gold ids.
  Files: `e2e/common/{corpus.jsonl,taxonomy.yaml,prompt.md,seeds.json,expected.json}`, `tests/test_e2e_folder.py`.

- [X] T005 `e2e/common/support.py`, plain functions, no class hierarchy, with tests added to `tests/test_e2e_folder.py` (red first). It provides: `corpus_rows()` / `taxonomy()` / `prompt()` / `seeds()` / `expected()` loaders over `e2e/common/` (taxonomy via `yaml.safe_load` into `hn.Taxonomy`); `StandIn` (an `Embedder` over `TestEmbeddingModel` whose `embed_query` returns the `seeds.json` vector for a phrase and raises `KeyError` naming an unknown phrase, the way `tests/test_table.py`'s `StubEmbedder` does); `check(name, got, want)` which on mismatch raises `Failed(f"{name}: expected {want!r}, got {got!r}")`; `run(main)` which prints progress as plain text, ends with exactly one `RESULT: pass`, `RESULT: skipped - <reason>` or `RESULT: fail - <message>` line, and exits 0 for pass and skipped and 1 for fail (an unexpected exception is a fail whose message is the exception); `container(example, image, port, env, ready)` as a context manager that sweeps stale containers with label `hunches-e2e=<example>`, runs `podman run -d --rm --name hunches-e2e-<example>-<pid> --label hunches-e2e=<example> -p 127.0.0.1::<port>`, reads the host port back with `podman port`, waits for `ready(host_port)` up to 60 s (on timeout fail with `podman logs --tail 20`), and removes the container in `finally`, `atexit` and a SIGTERM handler; if `podman` is not on the PATH, fail with "podman is required: https://podman.io/docs/installation" and never try `docker`; `classify_and_evaluate(candidates, tmp, cache)` which copies `gold.jsonl` byte for byte into `tmp` (compares bytes after copying), prints `GOLD.md`, builds the `hn.Classifier("anthropic:claude-haiku-5-5", taxonomy, prompt)` with `cache=e2e/.cache`, prints `clf.estimate(...)` **before any live call**, returns `skipped` (not pass) with the reason when there is no `ANTHROPIC_API_KEY` and the estimate shows live calls, or when `gold.jsonl` is absent, otherwise runs `clf.classify(candidates, max_cost=0.50)` and `hn.evaluate(clf, gold.dev, target=score_floor, log=False)`, checks the score against `score_floor`, and prints `score=<value>`. Tests (offline, hand-written expectations): the `RESULT` line and exit status for each of pass/skipped/fail via `subprocess` on a tiny module in `tmp_path`; `check` message contains the name and both values; `StandIn` returns the seed vector and rejects an unknown phrase; with `PATH` emptied `container(...)` fails with the podman message and the text never contains `docker`; `classify_and_evaluate` with no key returns skipped after printing the estimate and calls no model (use `FunctionModel` counting, per `tests/test_e2e.py`). Files: `e2e/common/support.py`, `tests/test_e2e_folder.py`.

**Checkpoint**: shared data and helper exist and are checked offline. **Human step H1 can happen now** (see Human steps); T006 onward does not wait for it, because evaluation steps skip cleanly until the gold file exists.

---

## Phase 3: User Story 1 - Table paths with no container (P1)

**Goal**: one example shows every way to load local data and get candidates.

**Independent test**: `uv run --with pyarrow python -m e2e.table.run` ends `RESULT: pass` (with a key and gold) or `RESULT: skipped - ...` (without), exit 0, no container needed.

- [X] T006 [US1] `e2e/table/run.py` and `e2e/table/README.md` (README per FR-002/FR-017: what it shows, needs, the one command, what a pass looks like, cost). The script writes the common corpus into a `TemporaryDirectory` as CSV (text and id only), Parquet, JSONL, and loads polars and pandas DataFrames and a list of rows from it. Steps, each a `check(...)` against `expected.json` / the corpus: (1) whole corpus from all seven forms gives the same ids in the same order (US1.1); the Parquet-through-pandas form is reported `skipped` by name if `pyarrow` is missing, never passed, and does not hide other failures; (2) keywords and regular expressions with ranking counts and `limit` on the file and the DataFrame, equal to each other and to `expected.json` (US1.2); (3) seeds over the JSONL, Parquet and DataFrame forms with `StandIn`, equal to the hand-computed similarities, bands and best seeds, and a CSV given `vector_column` is refused with the library's message (US1.3); (4) candidates from the whole corpus go to `classify_and_evaluate` (US1.4). Set `hn.settings.root` to the temporary folder. Evidence: run with no key (expect `skipped`), run once with an `expected.json` value changed in a scratch copy to show the failure message (US1.5; restore it), `git status --short` unchanged, run with `PYARROW` absent (plain `uv run`) to show the by-name skip. Files: `e2e/table/run.py`, `e2e/table/README.md`.

---

## Phase 4: User Story 2 - Postgres and pgvector (P1)

**Goal**: one example per Postgres path, each starting and removing its own database.

**Independent test**: `uv run python -m e2e.postgres.run` and `uv run python -m e2e.pgvector.run` each end `RESULT: pass` or `skipped`, exit 0, and `podman ps -a --filter label=hunches-e2e` is empty afterwards.

- [X] T007 [US2] `e2e/postgres/run.py` and `README.md`: image `postgres:16` (pull it once and record the tag in the README; if the plain image cannot be pulled, stop and report). Readiness by a `psycopg.connect` retry loop. Load the corpus (no vectors needed) as a one-table layout and as a two-table layout (`posts` and `texts`, joined on id), set `HUNCHES_PG_URL` in the process environment only (never written to a file), `ANALYZE` both. Checks: whole corpus and keywords equal `expected.json` and the table example's values for both layouts (US2.1, US2.2); the `%`, `_`, backslash terms and the inline-flag regex give identical hits and ranking with `server_side` on and off (US2.3); `PgCorpus(..., max_result_mb=<small>)` refuses the whole corpus with the limit in the message, and `limit=` and a keyword filter get past it (US2.5, research R7); candidates go to `classify_and_evaluate` (US2.6). Evidence as in the Phase 3 note. Files: `e2e/postgres/run.py`, `e2e/postgres/README.md`.

- [X] T008 [US2] `e2e/pgvector/run.py` and `README.md`: image `pgvector/pgvector:pg16`; `CREATE EXTENSION vector`; load the corpus with a `vector(2)` column; seeds with `StandIn` in `search="exact"` equal the hand-computed similarities of `expected.json` (US2.4); then create an HNSW index and run `search="index"`, which must return the same ids (raise `hnsw.ef_search` if a run shows otherwise, and say so in the README); candidates go to `classify_and_evaluate`. Evidence as before; also run `tests/test_pg_integration.py` once against the same container with `HUNCHES_TEST_PG_URL` set to prove the example's container is a valid target (report the count; it is not part of the commit). Files: `e2e/pgvector/run.py`, `e2e/pgvector/README.md`.

---

## Phase 5: User Story 3 - S3 Vectors on Floci (P2)

**Goal**: whole corpus, keywords and seeds against an S3 Vectors index without AWS.

**Independent test**: `uv run python -m e2e.s3.run` ends `RESULT: pass` or `skipped`, exit 0, no container left.

- [X] T009 [US3] `e2e/s3/run.py` and `README.md`: `podman pull floci/floci` and pin the tag actually pulled (replace `latest`; record it in the README, with the note that Floci is a stand-in and makes no claim about real AWS ordering, permissions or throttling). Readiness by a boto3 `list_vector_buckets` retry loop against the published port; set `AWS_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` to local fixed values in the process environment only. Bucket and index names at least 3 characters. Create the index with `dataType="float32"`, `dimension=2`, `distanceMetric="cosine"` and load the corpus with `put_vectors`, each vector `{"key": id, "data": {"float32": embedding}, "metadata": {"text": text}}` (the library reads `metadata["text"]`, `src/hunches/search.py`). Checks: whole corpus returns every id exactly once and the example says the service's listing order is not asserted (US3.1); keywords and seeds equal `expected.json` and the table example's values (US3.2); a second index holding 1,050 generated filler vectors (500 per `put_vectors` call, generated in the script, never committed) returns all 1,050 ids once, which crosses the library's 1,000-per-page listing (research R7); candidates go to `classify_and_evaluate` (US3.3). Evidence as before. Files: `e2e/s3/run.py`, `e2e/s3/README.md`.

---

## Phase 6: User Story 4 - The walkthrough (P2)

**Goal**: the detailed classify, estimate and evaluate walkthrough, as a notebook only, on the common data.

**Independent test**: a headless run (T011) executes every cell, or reports `skipped` at the model step when there is no key.

- [X] T010 [US4] Move and rebuild, one commit so the suite stays green. `git mv examples/sample/corpus.jsonl tests/fixtures/sample_corpus.jsonl` and point `tests/test_e2e.py` (its `SAMPLE` path and docstring) at it. Create `e2e/walkthrough/walkthrough.ipynb` (no stored outputs, `execution_count` null; build it with `nbformat` or by editing JSON) from `examples/sample/walkthrough.py`'s steps, rebuilt on `e2e/common/` (`Path("..") / "common"`, kernel cwd is the notebook folder): copy `gold.jsonl` byte for byte and show `GOLD.md` (the live `hn.label` cells are gone; the prose says people label in the labelling page and links `e2e/README.md`), `get_candidates` over the whole corpus and over seeds with a `StandIn` defined inline (the notebook imports nothing from `support.py`), `clf.estimate` before any call, a first cell that raises `RuntimeError("SKIPPED: set ANTHROPIC_API_KEY ...")` when there is no key and the estimate shows live calls, `evaluate` on dev with a `target`, disagreements, `with_prompt` and a second evaluation, `band_sample`, `classify` with `max_cost`, the test split evaluated once at the end, `eval_log()`, and `save`. `hn.settings.root` and `cache=` point at a temporary folder and `e2e/.cache`. Delete `examples/` (script, README, notebook), remove the `examples/**` line from `pyproject.toml`, and in `tests/test_docs.py` remove the script/notebook-twin test and `PY`, repoint `SAMPLE`/`IPYNB` at `e2e/walkthrough/`, and keep the honesty test's intent for the notebook (no `labelled_by`, no `import_rows`, no key text, no hand-written `labels=[`, only public names, parses). Write `e2e/walkthrough/README.md` (needs, cost placeholder "to be recorded after the first real run", how to open it in Jupyter, marimo or Colab). Evidence: `jupyter`-free check that the notebook JSON parses and its code compiles; the headless run itself is T011. Files: `tests/fixtures/sample_corpus.jsonl`, `tests/test_e2e.py`, `tests/test_docs.py`, `pyproject.toml`, `e2e/walkthrough/{walkthrough.ipynb,README.md}`, deletions under `examples/`.

---

## Phase 7: User Story 5 - Run-all, README and the drift checks (P3)

**Goal**: one command runs everything; users are pointed at `e2e/`; the folder stays current.

**Independent test**: `uv run --with pyarrow python -m e2e.run_all` prints one line per example and `all: ...`; `uv run pytest` fails when an example folder, link or name breaks.

- [X] T011 [US5] `e2e/run_all.py`: run `table`, `postgres`, `pgvector`, `s3` one after another with `subprocess` (`uv run [--with pyarrow] python -m e2e.<name>.run`), read each last `RESULT:` line, parse `score=`, then run the notebook with `nbclient.NotebookClient` (cwd `e2e/walkthrough`, kernel `python3`, not written back); a `CellExecutionError` whose message starts `SKIPPED:` is `skipped`, any other is `fail`. Print `<name>: <RESULT line>` per example, then `all: pass|fail|skipped`; exit 1 if any failed or if two examples printed different `score=` values (contract). Evidence: run it here with podman and no key (expect table/postgres/pgvector/s3 and walkthrough `skipped` after their candidate checks pass, `all: skipped`, exit 0); make one example fail and show exit 1; `podman ps -a --filter label=hunches-e2e` empty. Report that a key-using run was not possible in the sandbox. Files: `e2e/run_all.py`.

- [ ] T012 [US5] Docs, drift test and current state. (a) `e2e/README.md`: the naming overlap with `tests/test_e2e.py` explained; which folder for which corpus kind; prerequisites; the commands; what each costs (time and model spend placeholders to be filled after the first real run, FR-009); the maintainer procedure to produce the gold file (FR-019: fix corpus, taxonomy and prompt first; `Gold.draw` with a seed writes pending rows; a **person** labels them with `hn.label`; commit `gold.jsonl` as written and write `GOLD.md`; an agent never does this step and refuses if asked). (b) Root `README.md`: replace the `examples/sample` link at line 28 with a short section telling users `e2e/` is the reference for the different setups, one line per folder, linked. (c) `AGENTS.md`: Layout line for `examples/sample/` becomes `e2e/`; the human-checks list (Jupyter walkthrough path; the 007 checks that e2e now covers via emulators stay listed for real services only; add H1-H3); "Current state" says 008 implemented; Commands gain the run-all command. (d) `tests/test_e2e_folder.py`: every FR-001 path has its folder with `README.md` and `run.py` (the walkthrough: `README.md` and `walkthrough.ipynb`); the root README links each folder; each example README names its command, needs and cost; every `hn.<name>` used in `e2e/**/*.py` and the notebook is in `hunches.__all__` (reuse the helper in `tests/test_docs.py`); no file under `e2e/`, `specs/008-*`, `README.md` or `AGENTS.md` tells anyone to run `docker` (the constitution's rule text is the only allowed mention, so scan only `e2e/` and the READMEs); the notebook has no outputs; `e2e/` is not under `pytest`'s `testpaths`. Red first for the folder-completeness test by running it before (a)-(c). (e) Run the full checks and, for the report, `/ponytail-review` on the diff and `/ponytail-debt`. Files: `e2e/README.md`, `README.md`, `AGENTS.md`, `tests/test_e2e_folder.py`.

---

## Dependencies

T001 -> T002 -> T003 -> T004 -> T005 -> {T006, T007, T008, T009, T010} -> T011 -> T012. T006 first (the others reuse its ideas, not its code). T010 needs T005's loaders only conceptually (the notebook is self-contained). T011 needs every example and the notebook. T012 last.

## Human steps (agents report these and stop; never fake them)

- **H0, before T004's corpus is final**: Chris approves the corpus topic, labels and prompt (plan research R2). Also confirms the model choice (R1) or asks for `claude-haiku-4-5`.
- **H1, after T005**: Chris draws rows with `Gold.draw` (seeded) and labels about 40 of them (30 dev, 10 test) in the labelling page, then commits `e2e/common/gold.jsonl` and `e2e/common/GOLD.md` as written. Until then evaluation steps report `skipped`.
- **H2**: first real run with `ANTHROPIC_API_KEY`: `uv run --with pyarrow python -m e2e.run_all`; record elapsed time and model spend in each example README and the walkthrough README (target well under $1, SC-007); compare the spend with the provider's billing page (research R1); adjust `score_floor` if the real score is lower.
- **H3**: open `e2e/walkthrough/walkthrough.ipynb` in real Jupyter and in marimo or Colab.

## Implementation strategy

MVP is Phases 1-2 plus T006 (table example): it needs no container and proves the data, helper, reporting and cache. Then T007-T009 add the backends in parallel-in-spirit but sequential in commits, T010 retires `examples/`, T011-T012 tie it together. Stop and report after T005 so Chris can approve the corpus and label (H0, H1) while the examples are built.

## Notes

- Counts: 12 tasks. US1 1, US2 2, US3 1, US4 1, US5 2, shared 5.
- If a task would need to change `Gold`, the labelling server or the gold rule text, stop: that is out of scope and the gold rule is not negotiable.

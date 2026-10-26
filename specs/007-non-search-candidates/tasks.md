---

description: "Task list for non-search candidate sources"
---

# Tasks: Non-search candidate sources

**Input**: `specs/007-non-search-candidates/` (`spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/public-api.md`, `quickstart.md`)

**Prerequisites**: spec approved, plan reviewed, constitution v1.0.1. Environment: `uv sync --extra s3 --extra pg --extra rds` (not `--all-extras`, which pulls the heavy `local` extra). Baseline before any task: `uv run pytest` gives 450 passed, 17 skipped.

**Tests**: required here, not optional (constitution Principle IV): every task is red/green. Write the failing test first, run it, show it failing for the right reason, then make it pass and show that run. Expected values are written by hand in the test; never derived by running the code under test. Tests use the fake `psycopg`, the stubbed `boto3.client`, `tmp_path` and `monkeypatch.chdir`; never a real service.

**Organization**: one task is one commit (`007/TNN: ...`) on branch `ccr-26b50054-jcevqw`. Before every commit run `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pytest`, all green, with the output summaries reported; never `--no-verify`. Because the suite must pass after every commit, a rename or removal is done in the same task as every caller of it. A task does only what its line says. No task is `[P]`: nearly all of them edit `src/hunches/search.py` or `src/hunches/candidates.py`.

## Format: `- [ ] TNN [Story] Description with file path`

Story labels map to `spec.md`: US1 whole corpus, US2 keywords, US3 compatibility, US4 server-side, US5 remote readers, US6 tables.

## Phase 1: Setup

None. No dependency, config or tool is added (plan: "no new dependency").

---

## Phase 2: Foundational (blocks every story)

**Purpose**: the result type must be able to say where a list came from before anything can produce a list that was not built from seeds. This task also delivers US3 (spec FR-009, FR-010, FR-011, FR-013): after it, everything old still behaves as before.

- [ ] T001 Add `source` to `Candidates` in `src/hunches/candidates.py` and guard the similarity-only operations in `src/hunches/evaluation.py`. Red first, in `tests/test_candidates.py`, `tests/test_evaluation.py` and `tests/test_notebook.py`:
  - `Candidates` gets a last field `source: str = "seeds"` (so every existing positional construction and every old file is unchanged). For `"keywords"` and `"all"`, `floor`, `seeds_digest` and `embedding_model` are `None` and `capped` is `False`; rows are `{id, text}` and, for keywords, also `terms_matched` and `matches`.
  - `above`, `bands`, `top_seeds` and `evaluation.band_sample` raise `ValueError("<name> needs similarity scores, but this list was built from <source>, not from seeds")` for a non-seed source and behave exactly as before for seeds.
  - `write` stores `"source"` in the `.meta.json` (and `null` for `floor` outside seeds); `read` returns `meta.get("source", "seeds")`, so a file with no `source` key loads as a seed result with its bands (use the existing `tests/fixtures/pre006/candidates.jsonl` and `.meta.json` for that test) and a keyword or `all` list round-trips with its source and its rank values.
  - `__repr__` and `_repr_html_`: seeds output unchanged; otherwise `N candidates (from keywords)` or `N candidates (whole corpus)`, no bands, a `terms_matched` and `matches` table for keywords. Assert that the text and HTML of a keyword list and an `all` list contain none of the words `floor`, `similarity`, `seed` or `band` (spec SC-004). `_repr_html_` escapes every cell and sets no colour (extend `test_every_object_returns_a_string_and_escapes_item_text` and `test_no_colour_anywhere` in `tests/test_notebook.py` with a keyword and an `all` list holding `<script>` text).
  - `sample`, `to_polars`, `to_pandas` work on every source (hand-built lists in the tests).
  Files: `src/hunches/candidates.py`, `src/hunches/evaluation.py`, `tests/test_candidates.py`, `tests/test_evaluation.py`, `tests/test_notebook.py`.

**Checkpoint**: seed behaviour byte-for-byte unchanged (existing tests are not edited except to add cases); non-seed lists can be built by hand.

---

## Phase 3: User Story 6 - Bring your own table (Priority: P1)

**Goal**: a corpus can be a CSV, Parquet or JSONL file, a pandas or polars DataFrame or a list of rows, and `LocalCorpus` is gone. This comes before US1 because US1 and US2 need a corpus to read.

**Independent Test**: spec "Independent Test" of story 6, and quickstart section 1 for the seed side.

- [ ] T002 [US6] Add `Table` and make seed search read a table once; `LocalCorpus` stays until T003, so this commit is purely additive. Red first, in new `tests/test_table.py`:
  - In `src/hunches/search.py`: `@dataclass(frozen=True, eq=False) class Table` with fields `source`, `text_column="text"`, `id_column=None`, `vector_column=None`, `embedding_model=None`. `__post_init__` refuses a CSV path with `vector_column` set (a CSV cannot hold a list of numbers) and an empty `text_column`.
  - `table_rows(table) -> list[dict]` with plain `if`s on the source: `str`/`Path` by suffix (`.csv` via `csv.DictReader` with `encoding="utf-8-sig"`; `.jsonl` via `json`; `.parquet` through polars if importable, else pandas, else an `ImportError` naming both; any other suffix is a `ValueError` listing `.csv`, `.parquet`, `.jsonl`); an object with `to_dicts` (polars) or `to_dict` (pandas, called as `to_dict("records")`) converted without importing either library; a plain list of dicts as is. Validation, naming the column or the first offending row: missing named column; text "not a non-empty `str`" (empty and whitespace-only refused; a pandas `nan` is not a `str`); missing id; repeated id. Ids become `str`; with no `id_column` the id is `str(position)`. Rows are never dropped, repaired or invented.
  - `search_table(table, vectors, floor, embedding_model) -> (per_seed, capped)` shaped like `search_pg_exact`: refuse with the contract messages when `vector_column` is `None` ("the table has no embedding column; keywords and the whole corpus need none"), when `embedding_model` is `None`, or when it differs from the embedder's (show both names); then read the table once, build the float32 matrix once (a vector that is not a list of numbers, or of a different length than row 0, fails naming its position), normalise once, one matrix product for all seeds, return per seed `[(id, text, similarity)]` with similarity at or above the floor, best first; `capped` is `False`. Same arithmetic as the local branch of `search_vectors`.
  - In `src/hunches/candidates.py` `asearch`, add `if isinstance(corpus, Table): per_seed, capped = await asyncio.to_thread(search_table, ...)` beside the pgvector exact branch. Export `Table` in `src/hunches/__init__.py` and `tests/test_public_api.py`.
  - Tests (hand-written expectations): the same five rows given as CSV, JSONL, Parquet (written with polars, `pytest.importorskip("polars")`), a polars frame, a pandas frame, a list of dicts, and (skipped unless `pyarrow` imports) a Parquet file read through pandas all give identical `table_rows`; each validation failure above; a `.parquet` path with both `polars` and `pandas` made unimportable (`monkeypatch.setitem(sys.modules, "polars", None)`) raises the `ImportError` naming both; an unknown suffix raises the `ValueError`; the `.csv` with `vector_column` refusal; the three `search_table` refusals; two seeds over a 4-row table give hand-computed similarities, order and floor cut; a CSV with a BOM keeps its first column name; `import hunches` still imports none of polars or pandas (the existing `tests/test_public_api.py` subprocess check must keep passing).
  Files: `src/hunches/search.py`, `src/hunches/candidates.py`, `src/hunches/__init__.py`, `tests/test_table.py`, `tests/test_public_api.py`.

- [ ] T003 [US6] Remove `LocalCorpus` and migrate everything that used it (spec FR-024). Red first: extend `tests/test_docs.py` and `tests/test_skills.py` so the README, `skills/hunches/**` and `docs/agent-instructions.md` blocks contain no `LocalCorpus`, `vectors.npy` or `items.jsonl` folder-layout text; they fail while the old text is there. Then:
  - Delete `LocalCorpus` and the `LocalCorpus` branch of `search_vectors` in `src/hunches/search.py` (keep its S3 and pgvector-index branches); remove it from `src/hunches/__init__.py`, `tests/test_public_api.py` and the type hints in `src/hunches/candidates.py`.
  - Migrate the users so the suite stays green: `tests/test_corpus.py`, `tests/test_search.py`, `tests/test_search_pg_index.py`, `tests/test_candidates.py`, `tests/test_e2e.py`, `tests/test_pg_integration.py`; `tests/test_pre006_fixtures.py` and `tests/fixtures/pre006/` (the three-file `corpus` folder becomes one `corpus.jsonl` with an `embedding` column; rewrite `test_corpus_is_well_formed` and the `search_vectors(LocalCorpus(...))` call to use `Table` and `search_table`, keeping the numbers in `expected.json` unchanged; update `tests/fixtures/pre006/README.md` to say the corpus fixture was converted and the other files are unchanged pre-006 output).
  - The example: `examples/sample/corpus/` becomes `examples/sample/corpus.jsonl` (`id`, `text`, `embedding`; the 2-D vectors; used as `Table("corpus.jsonl", vector_column="embedding", embedding_model="hand-built-2d")`); `examples/sample/walkthrough.py`, `walkthrough.ipynb` (same cells; `tests/test_docs.py` and `tests/test_notebook.py` enforce it) and `examples/sample/README.md` change together.
  - Minimal doc edits where the removed name appears: the one `LocalCorpus` line in `README.md` and `skills/hunches/references/workflow.md`, and the layout line in `AGENTS.md`. Describing the table format and the "already embedded" wording is T010.
  Files: `src/hunches/search.py`, `src/hunches/candidates.py`, `src/hunches/__init__.py`, the test and fixture files above, `examples/sample/*`, `README.md`, `AGENTS.md`, `skills/hunches/references/workflow.md`.

**Checkpoint**: seed search works over a `Table`; no trace of `LocalCorpus` remains in code, tests, fixtures, example or docs.

---

## Phase 4: User Story 1 - Classify the whole corpus (Priority: P1) - MVP

**Goal**: one entry point, `get_candidates`, replaces `search`; with only a corpus it returns the whole corpus.

**Independent Test**: spec story 1 scenarios 1 to 5 and quickstart sections 1 and 3 (whole-corpus parts).

- [ ] T004 [US1] Rename `search` and `asearch` to `get_candidates` and `aget_candidates`, seeds only, in the final calling style so no caller is edited twice. Red first, in `tests/test_candidates.py`:
  - Signature `get_candidates(corpus, *, seeds, embedder, floor=None, limit=None, out=None, cache=None)`; `aget_candidates` is the same with `async def`; the sync form is `_sync.run(aget_candidates(...))`. The old body of `asearch` is the body (`floor=None` means `FLOOR`). New here: `limit` keeps the N most similar (`rows[:limit]` after the sort); `limit` below 1 refused; an empty `seeds` list refused (naming `seeds`); a bare `str` for `seeds` is the `TypeError` it already is. No `keywords`, `regex` or `server_side` parameters yet and no stubs for them; they arrive with the code that implements them (T006, T009).
  - The rename sweep, so no caller breaks: `src/hunches/__init__.py` (`__all__`: remove `search`, `asearch`; add `get_candidates`, `aget_candidates`), `tests/test_public_api.py`, every test file that calls them (a call `search(corpus, seeds, embedder=e)` becomes `get_candidates(corpus, seeds=seeds, embedder=e)`): `tests/test_candidates.py`, `test_e2e.py`, `test_evaluation.py`, `test_notebook.py`, `test_label_page.py`, `test_pg_integration.py`, `test_pre006_fixtures.py`, `test_search.py`, `test_search_pg_*.py`, `test_skills.py`, `test_docs.py`, `test_corpus.py` (grep each for `search(`, `asearch`, `import_module("hunches.search")` and fix only real calls), `tests/fixtures/pre006/README.md`, `examples/sample/walkthrough.py` and `.ipynb`, `README.md`, `skills/hunches/SKILL.md`, `skills/hunches/references/workflow.md`, `AGENTS.md`. Rewrite the `AGENTS.md` "Package quirk" paragraph to name only `hunches.cost` and `hunches.settings` (`hunches.search` is the submodule again; the pg tests' `importlib.import_module("hunches.search")` still works).
  Files: `src/hunches/candidates.py`, `src/hunches/__init__.py`, the test, example and doc files above.

- [ ] T005 [US1] Make `seeds` optional: with no filter `get_candidates` returns the whole corpus (spec FR-001, FR-005, FR-007, FR-008, FR-025 for what exists so far). Red first, in `tests/test_candidates.py`:
  - Signature becomes `seeds=None`. No filter: the whole corpus in table order as `Candidates(source="all")`, rows `{id, text}`, as an iterator of `(id, text)` pairs passed through `itertools.islice` for `limit`; for a `PgCorpus` or `S3Corpus` a one-line `NotImplementedError("... whole-corpus reads arrive with the Postgres/S3 reader")` that T007 and T008 delete. Argument rules (message names the argument): `embedder`, `floor` or `cache` without `seeds` refused; seeds without `embedder` refused.
  - Async and loop: the whole read runs in one `asyncio.to_thread` call (research R12); test that the reader runs on a thread other than the event loop's (record `threading.get_ident()` in a monkeypatched reader) and that the sync `get_candidates` works when called inside a running event loop (an `async def` test calling it directly).
  - Default output: `out` a path writes it for every source; `out=None` writes `<settings.root>/candidates.jsonl` for seeds only; `out=False` writes nothing. Test: a seed search, then `get_candidates(table, limit=5)`, leaves the seed result's file byte-identical.
  - Tests (hand-written): whole table in order; `limit=2` keeps the first two; an empty table gives an empty result that says `0 candidates`; two rows with the same text and different ids stay separate; the argument refusals; the same five rows from each of the six table forms (T002's list) give identical `get_candidates` results (spec SC-009).
  - Downstream use of an `all` list, one hand-built test each: `Gold.draw` in `tests/test_gold.py`, `Classifier.estimate` and `classify` in `tests/test_classifier.py` (count `FunctionModel` calls; spec FR-012, SC-001).
  Files: `src/hunches/candidates.py`, `tests/test_candidates.py`, `tests/test_gold.py`, `tests/test_classifier.py`.

**Checkpoint (MVP)**: `get_candidates(Table(...))` gives the whole table; `get_candidates(table, seeds=..., embedder=...)` is today's semantic search; nothing is broken.

---

## Phase 5: User Story 2 - Ranked keyword and regex candidates (Priority: P2)

**Goal**: `keywords=` with plain terms, regex strings and compiled patterns that keep their own flags, ranked, limited.

**Independent Test**: spec story 2 scenarios and quickstart section 2.

- [ ] T006 [US2] Add the `keywords` and `regex` parameters and the keyword branch of `get_candidates` in `src/hunches/candidates.py`. Red first, in `tests/test_candidates.py`, on a 5-row hand-written table with the expected ids and order written out:
  - Write the match-and-rank loop as one function over an iterator of `(id, text)` pairs (not over a `Table`), so the Postgres and S3 readers in T007 and T008 reuse it without a refactor.
  - Term compile (before any read): a plain string is `re.compile(re.escape(t), re.IGNORECASE)`; with `regex=True` a string is `re.compile(t)` (inline flags still work); a compiled `re.Pattern` is used as given. Refuse (naming the term) a blank string and a pattern for which `p.match("")` succeeds, with the one-line comment `# shortcut: only patterns matching the empty string are refused, zero-width ones like \b still match every word, tell the user in the docs`. An invalid regex raises `re.error` naming the pattern before the table is read.
  - Per item: `terms_matched` is the number of patterns with at least one match, `matches` is the sum over patterns of `sum(1 for _ in p.finditer(text))`; an item with `terms_matched == 0` is not a hit. Rank by `(-terms_matched, -matches, index)` where index is the read position; with a limit `heapq.nsmallest(limit, hits, key=...)`, without `sorted`. Rows are `{id, text, terms_matched, matches}`, `source="keywords"`.
  - Argument rules (message names the argument): `seeds` together with `keywords` refused ("one filter per call"); an empty `keywords` list refused; a bare `str` is a `TypeError` in the style of seeds; `regex=True` without `keywords` refused.
  - Tests (hand-computed): any-term matching includes an item once; case-insensitive for plain strings (`Ballot`, `BALLOT`); `strasse` does not match `Straße`; the same string with `regex=False` (literal) and `regex=True` (pattern); three compiled patterns with different flags (`re.I`, none, `re.S`) each apply only their own flags; ranking order incl. a tie kept in table order; `limit=3` of ten hits keeps the three best; no match gives an empty result that says `0 candidates`; blank term, `p.match("")` pattern and invalid regex refusals; `.above()` on the result raises naming "keywords"; a table whose `vector_column` holds garbage still keyword-searches fine (spec edge case); no file is written unless `out` is a path.
  Files: `src/hunches/candidates.py`, `tests/test_candidates.py`.

**Checkpoint**: US1 and US2 work over any `Table`; every story testable without a network.

---

## Phase 6: User Story 5 - Big remote corpora (Priority: P3)

**Goal**: whole-corpus and Python-side keyword reads over Postgres and S3 Vectors, read-only, vectors never touched.

**Independent Test**: spec story 5 scenarios with the fake `psycopg` and the stubbed `boto3.client`.

- [ ] T007 [US5] Read a `PgCorpus` without vectors, in `src/hunches/search.py` (reader) and `src/hunches/candidates.py` (wiring into the whole-corpus branch and T006's loop), tests in new `tests/test_search_pg_keywords.py` using the same `Conn`/`Cur` fake pattern as `tests/test_search_pg_exact.py`. Red first:
  - Reader over `pg_connect(corpus)` with a named server-side cursor, `itersize = PG_BATCH`, identifiers from `psycopg.sql.Identifier(*name.split(".", 1))`, never calling `extension_version` or `column_type` (so a table with no vector column or vector extension works). Single table: `SELECT {id}, {text} FROM {table} ORDER BY {id}`. Two tables (`text_table` set; use `text_source`): `SELECT t.{id}, x.{text} FROM {table} t LEFT JOIN {text_table} x ON x.{text_id} = t.{id} ORDER BY t.{id}`; a `NULL` joined text raises `RuntimeError("no text row for id '<id>'")`. Ids as `str`. Errors through `pg_message`; connection closed in `finally`.
  - Whole corpus: refuse before reading when the planner estimate (`table_estimates`, as `search_pg_exact` does) times the row overhead exceeds `max_result_mb`, and abort while streaming when the received size does (reuse the `count` accounting, `PG_ROW_OVERHEAD`, and `_too_large`'s wording adapted to "Use a keyword filter, a limit, or raise PgCorpus(max_result_mb=...)"); `max_result_mb=0` means no limit. Python-side keywords call T006's loop on the streamed pairs and keep only hits (at most `limit`); nothing is written. Delete T005's `NotImplementedError` for `PgCorpus`; the blocking read runs inside T005's single `to_thread`.
  - Tests: single-table statement text and ordering; two-table statement text and the missing-text-row error; a table with no vector column and no extension works: assert from `conn.executed` that only the reader's statements ran (no version or column query); a seed search (`get_candidates(pg, seeds=..., embedder=...)`) on a table with no embedding column fails with a message naming that column (spec FR-019, story 4 scenario 6); `itersize == PG_BATCH` and the cursor is named; whole-corpus over the limit refuses with the limit in the message; keyword search over 30 canned rows returns only the 3 hand-picked hits ranked as expected, with `limit=2` keeping the best two; every executed statement starts with `SELECT` (read-only).
  Files: `src/hunches/search.py`, `src/hunches/candidates.py`, `tests/test_search_pg_keywords.py`.

- [ ] T008 [US5] Read an `S3Corpus` without vectors, in `src/hunches/search.py` with wiring in `src/hunches/candidates.py` and tests in `tests/test_search.py`. Red first:
  - Manual loop over `client.list_vectors(vectorBucketName=corpus.bucket, indexName=corpus.index, returnMetadata=True, maxResults=1000)` following `nextToken` (house style: `search_vectors` loops by hand). Item = `(v["key"], v["metadata"]["text"])`; a missing `text` key is an error as in `search_vectors`. `returnData` is never passed. A botocore `ClientError` with code `AccessDeniedException` is re-raised as a `RuntimeError` naming `s3vectors:ListVectors` and `s3vectors:GetVectors`. Order is the service's; a `limit` keeps the first N listed.
  - Wire whole-corpus and Python-side keyword search for `S3Corpus` (delete T005's last `NotImplementedError`).
  - Tests with the stub `FakeS3` in `tests/test_search.py` extended with a `list_vectors` returning two pages (response shape `{"nextToken": ..., "vectors": [{"key": ..., "metadata": {"text": ...}}]}`, the documented shape verified against boto3 1.43.108): both pages are read; `returnMetadata` is `True` and `returnData` is absent from the recorded calls; a keyword search keeps only hits; a 403 stub error names both permissions; a missing `text` is an error; no write method of the stub is ever called.
  Files: `src/hunches/search.py`, `src/hunches/candidates.py`, `tests/test_search.py`.

**Checkpoint**: all three corpus kinds work for the whole-corpus and Python-side keyword paths.

---

## Phase 7: User Story 4 - Server-side filtering on Postgres (Priority: P3)

**Goal**: `server_side=True` makes Postgres do the matching; ranking and `limit` stay in the library.

**Independent Test**: spec story 4 scenarios with the fake `psycopg` (statement text and parameters only; the real-database comparison is a human check).

- [ ] T009 [US4] Add the `server_side` parameter and the server-side keyword filter in `src/hunches/search.py` and `src/hunches/candidates.py`; tests in `tests/test_search_pg_keywords.py`. Red first:
  - Same reader as T007 with a `WHERE` appended: plain-text terms `{text} ILIKE ANY(%s::text[])` where each element is `%` + term + `%` with `\`, `%` and `_` each escaped by a backslash (backslash is `LIKE`'s default escape); with `regex=True` strings `{text} ~ ANY(%s::text[])` with the strings unchanged. Two-table layout: `FROM {table} t JOIN {text_table} x ON x.{text_id} = t.{id} WHERE x.{text} ...`. The one parameter is a list of strings; no user text ever appears in the statement text. One cursor, read-only.
  - Argument rule and refusals (before any connection is opened): `server_side=True` without `keywords` refused; with a compiled `re.Pattern` names the term and says server-side regular expressions are strings with `regex=True` in the database's syntax; on a `Table` or `S3Corpus` says only a Postgres corpus can filter on the server. A server-side regex string is not compiled by Python for validation (the database rejects an invalid one; its error, through `pg_message`, names the term).
  - Ranking recount: returned rows are matched in Python by T006's loop to get `terms_matched` and `matches`; a row that counts zero is kept and ranks last, and one `warnings.warn(UserWarning)` names each term that Python could not compile or that counted zero on a returned row.
  - Tests (hand-computed): the exact statement text for plain, regex and two-table cases and the exact parameter list for a term `a%b_c\d` (expected element `%a\%b\_c\\d%`); no term text inside the statement (assert on the statement string with a term containing `'; DROP`); the refusals; a canned answer ranked and limited like the Python side; the zero-count warning fires once and the row is last.
  Files: `src/hunches/search.py`, `src/hunches/candidates.py`, `tests/test_search_pg_keywords.py`.

**Checkpoint**: every functional requirement in `spec.md` has code and tests.

---

## Phase 8: Polish and cross-cutting

- [ ] T010 Documentation and wording sweep (spec FR-017, FR-019; research R9). Red first: extend `tests/test_docs.py` and `tests/test_skills.py` so the README, `skills/hunches/SKILL.md`, `skills/hunches/references/*.md` and `docs/agent-instructions.md` blocks use `get_candidates` and `Table`, contain no `hn.search(`, and no longer call the library "already embedded" (the drift tests already print the text to paste when a copy drifts). Then:
  - Describe the candidate call and when to prefer seeds, keywords or the whole corpus, and the table format a user should provide (text column, optional id column, embedding column and model for seed search, accepted files and DataFrames), in `README.md`, `skills/hunches/SKILL.md`, `skills/hunches/references/workflow.md`, `docs/agent-instructions.md` (kept equal to the README block), `.kiro/steering/hunches.md`. Say that `\b`-style zero-width patterns still match every word, that server-side regex strings use Postgres syntax, that S3 listing order is the service's, and that Postgres rows are read in ascending id order. Never mention the removed corpus or its folder layout.
  - Stop calling the library "already embedded": `pyproject.toml` `description`, `src/hunches/__init__.py` docstring, `plugin.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (two descriptions), `skills/hunches/SKILL.md` description and first paragraph (its description must still end with `GOLD_RULE_SHORT`; `tests/test_skills.py` must pass), `skills/hunches/references/workflow.md` first line, `README.md` first paragraph, `AGENTS.md` "What this repo is" (to match constitution v1.0.1), and the `AGENTS.md` layout and "Current state" sections (add 007 as implemented and list what a human still has to do: the real-Postgres, real-S3 and Parquet-engine checks from `quickstart.md` section 5).
  - Do not touch `src/hunches/gold_rule.md` or any gold-rule text.
  Files: the documentation, manifest and drift-test files listed.

- [ ] T011 Final verification and report (no new code). Run `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pytest` and `uv build` (wheel must contain `hunches/web/*` and `hunches/gold_rule.md`) and report the real summaries; run `quickstart.md` sections 1 to 4 in a scratch script under the scratchpad directory (not committed) and report the outputs; run `/ponytail-review` on the whole branch diff and `/ponytail-debt`, fix what the review finds as new fix-only commits (`007/T011: ...`), and report both. Final report per the constitution: what changed, files touched, red/green evidence, check outputs, deviations from the spec, the Ponytail line, and the human-only items (real Postgres including the two-table layout and server-side vs Python-side results; a real S3 Vectors index; Parquet through polars and through pandas with pyarrow; the walkthrough in real Jupyter with a real key; the labelling page in a browser as `AGENTS.md` already lists).
  Files: none (reports only; fix-only commits where the review demands).

---

## Dependencies and execution order

- T001 first (every later task builds non-seed lists).
- T002 and T003 before T004: `LocalCorpus` must be gone before the rename sweep touches the same files, and the whole-corpus branch (T005) needs a corpus to read.
- T004 before T005, T005 before T006 (the keyword branch plugs into the same function), T006 before T007 and T009 (the match loop is shared), T007 before T009 (server-side is the same reader plus a `WHERE`), T008 independent of T007 and T009 in content but sequential because it edits the same files.
- T010 after T009 (the docs describe finished behaviour; the drift tests stay green meanwhile through T003 and T004's minimal edits). T011 last.
- Story order by priority is the build order: foundation, US6 (P1), US1 (P1), US2 (P2), US5 and US4 (P3). US3 (compatibility) is delivered by T001 and held by every task keeping the existing tests green.

## Parallel opportunities

None worth the merge risk: T002 to T009 all edit `search.py` or `candidates.py`.

## Implementation strategy

- **MVP**: T001 to T005. After them a user can build a table from a file or DataFrame and get the whole corpus or a semantic search through one function, and nothing is broken.
- **Incremental**: T006 adds keywords; T007 and T008 add the remote readers; T009 adds the server-side filter; T010 aligns the words; T011 proves and reports. Each commit leaves the suite green.
- Per the constitution: run `/ponytail-review` on `spec.md`, `plan.md` and this file before `/speckit-implement`, and again on the diff afterwards.

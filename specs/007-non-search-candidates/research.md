# Research: Non-search candidate sources

**Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

Each item: what was decided, why, what else was weighed. "Verified" marks a fact checked on
2026-10-26 against the installed package or the current documentation (linked); "Not verified"
marks what only a human with a real service can check.

## R1. One entry point, dispatching with plain `if`s

- **Decision**: `get_candidates` / `aget_candidates` in `candidates.py` replace `search` /
  `asearch`. After argument validation it runs one of three branches: seeds (today's code,
  moved unchanged into a private function), keywords, or the whole corpus.
- **Rationale**: constitution Principle II ("where two behaviours must coexist use a plain `if` in
  one function"); the existing `search`/`asearch` pair already shows the sync-over-async idiom
  (`_sync.run`).
- **Rejected**: three public functions (the user rejected `everything`); a strategy or filter
  class (an abstraction for three branches).

## R2. `Table` replaces `LocalCorpus`, in `search.py`

- **Decision**: a frozen dataclass `Table(source, text_column="text", id_column=None,
  vector_column=None, embedding_model=None)` beside `S3Corpus` and `PgCorpus`, declared with
  `eq=False` (a DataFrame field makes the generated `__eq__` ambiguous; nothing compares or hashes
  corpora). `LocalCorpus` is deleted outright (library unpublished; spec FR-024).
- **Reading** (one function, `table_rows(table) -> list[dict]`, plain `if`s on the source):
  - a `str`/`Path`: by suffix. `.csv` with the standard `csv.DictReader` (`utf-8-sig`, so an
    Excel BOM does not rename the first column); `.jsonl` with `json`; `.parquet` through polars
    if importable, else pandas, else an error naming both; any other suffix is an error listing
    the accepted ones.
  - an object with `to_dicts` (polars) or `to_dict` (pandas): `df.to_dicts()` /
    `df.to_dict("records")`. No import of either library; duck-typed. A list of dicts is used as
    is.
- **Verified** (installed here: polars 2.1.0, pandas 3.1.0, no pyarrow): both conversions give
  `[{'id': 'a', 'text': 'x', 'emb': [0.1, 0.2]}, ...]` on a small frame.
  [`pandas.read_parquet`](https://pandas.pydata.org/docs/reference/api/pandas.read_parquet.html)
  "requires the pyarrow library" (fastparquet is deprecated as an engine since pandas 3.1), so
  without pyarrow pandas cannot read Parquet here;
  [`polars.read_parquet`](https://docs.pola.rs/api/python/stable/reference/api/polars.read_parquet.html)
  needs no extra dependency by default. Hence polars first, pandas second.
- **Validation** (spec FR-021) in the same function: missing named column; text not a `str`, or
  empty/whitespace (pandas turns missing values into `nan`, which is not a `str`); id missing;
  repeated id (first one named). Ids become `str` (as `Gold` and the pgvector reader already do).
  No id column: id is `str(position)`.
- **Vectors**: read only when the seeds branch needs them: `numpy.asarray(..., float32)` of the
  column; a row that is not a list of numbers, or has a different length from row 0, fails naming
  its position. A `.csv` source with `vector_column` set is refused in `__post_init__` (a CSV
  cannot hold a list of numbers), the one check done at construction, because it needs no I/O.
- **Rejected**: a generic reader registry (spec: no registry); a `Table.from_*` constructor per
  format (more public names than one `source` argument); carrying extra columns into candidates
  (spec: skipped).

## R3. Keyword matching

- **Decision**: every term becomes a `re.Pattern`: a plain string is `re.compile(re.escape(t),
  re.IGNORECASE)`, or `re.compile(t)` when `regex=True` (inline flags such as `(?i)` still work);
  a compiled pattern is used as given with its own flags. Per item: `terms_matched` is the number of
  patterns with at least one match, `matches` is the sum of `sum(1 for _ in p.finditer(text))`
  over patterns (non-overlapping). An item with `terms_matched == 0` is not a hit.
- **Verified** (Python 3.12 here): `re.search("strasse", "Straße", re.I)` is `None` (no
  full folding, as the spec says), but `re.I` also treats `ſ` as `s` (documented simple
  case-insensitive matching; the spec now says "Python's simple case-insensitive matching").
  Flags are per pattern, so one pattern's flags cannot leak into another
  ([`re`](https://docs.python.org/3/library/re.html): `Pattern.flags` carries them).
- **Validation**: Python compiles the patterns before any read, except the regex strings of a
  `server_side=True` call, whose syntax is the database's (Python must not reject valid Postgres
  syntax); there the database's error is the check. A bare `str` instead of a list is a `TypeError` (as `seeds` today); an empty list,
  an empty/blank term, or a pattern for which `p.match("")` succeeds is a `ValueError` naming it.
  The last check misses zero-width patterns such as `\b` (it does not match `""`), marked in code
  `# shortcut: only patterns matching the empty string are refused, zero-width ones like \b still
  match every word, tell the user in the docs`.
- **Rejected**: counting with `findall` (returns groups when the pattern has any); a scoring
  function option (spec: skipped).

## R4. Ranking and `limit` in one streaming pass

- **Decision**: stream items through the patterns; keep a hit as `(terms_matched, matches, index,
  row)`. Order key `(-terms_matched, -matches, index)` (index = position read, i.e. corpus order).
  With a limit use `heapq.nsmallest(limit, hits, key=...)` over the generator, which holds only
  `limit` rows; without one, `sorted`. Whole corpus with a limit: `itertools.islice`.
- **Rationale**: standard library; memory is bounded by `limit` (spec FR-014) with no extra code.
- **Seeds with a limit**: `rows[:limit]` after the existing sort (already best first).

## R5. Reading Postgres without vectors, and the server-side filter

- **Decision**: new functions in `search.py` using the existing `pg_connect` (read-only,
  repeatable read), `text_source`, `pg_message`, `PG_BATCH` and a named server-side cursor with
  `itersize = PG_BATCH` (the pattern `search_pg_exact` uses for step 2):
  - single table: `SELECT {id}, {text} FROM {table} [WHERE <filter>] ORDER BY {id}`;
  - two tables (`text_table` set): `SELECT t.{id}, x.{text} FROM {table} t LEFT JOIN {text_table}
    x ON x.{text_id} = t.{id} [WHERE <filter on x.{text}>] ORDER BY t.{id}`. A row whose joined
    text is `NULL` raises `no text row for id '...'` (the message `search_pg_exact` already uses).
    With the filter the LEFT JOIN is moot (a `NULL` text never matches), so an id missing its text
    row is detected only on the unfiltered read; stated in the contract.
  - identifiers through `psycopg.sql.Identifier(*name.split(".", 1))` as the existing code does.
- **Filter** (only with `server_side=True`; never user text in the statement):
  - plain-text terms: `{text} ILIKE ANY(%s::text[])` with the parameter a list of `%term%` where
    each term has `\`, `%`, `_` escaped with a backslash (backslash is `LIKE`'s default escape);
  - regex strings: `{text} ~ ANY(%s::text[])` with the strings unchanged (case-sensitive; flags
    inline).
  - the explicit `::text[]` cast copies what `search_pg_exact` already does (`unnest(%s::text[])`,
    `search.py:350`), so the statement does not depend on how the driver types a list of strings.
- **Verified** against the PostgreSQL documentation
  ([pattern matching](https://www.postgresql.org/docs/current/functions-matching.html),
  [`ANY`](https://www.postgresql.org/docs/current/functions-comparisons.html)): `ILIKE` is
  case-insensitive "according to the active locale", the default escape is the backslash, `~` is
  the case-sensitive POSIX match, embedded options like `(?i)` go at the start of the pattern, and
  `expr operator ANY (array)` accepts any Boolean operator (`'abc' ILIKE ANY ('{A%,x%}')` is true).
  The generated SQL text is asserted in tests with the fake `psycopg`; whether a real Postgres
  returns the right rows is **Not verified** (human check, spec Verification).
- **Result-size guard**: reuse the `count(...)` accounting idea from `search_pg_exact`
  (`PG_ROW_OVERHEAD`, `max_result_mb`) for the whole-corpus read only; keyword reads keep just the
  hits, so they are bounded by the hits, not the table. The planner-estimate pre-check
  (`table_estimates`) is reused up front for whole-corpus reads.
- **Rejected**: translating Python flags to Postgres (spec decision: refuse compiled patterns);
  `regexp_count` or `ts_rank` for ranking (version dependence; the spec ranks in the library);
  `COPY` or client-side streaming of the whole table for server-side mode (defeats its purpose).

## R6. Reading S3 Vectors without vectors

- **Decision**: a manual `nextToken` loop over `client.list_vectors(vectorBucketName=...,
  indexName=..., returnMetadata=True, maxResults=1000)` (house style: `search_vectors` already
  loops on `nextToken` by hand). Item = `(v["key"], v["metadata"]["text"])`; a missing `text` key is
  an error, as in `search_vectors`. Vectors are never requested (`returnData` defaults to false).
  A `ClientError` with code `AccessDeniedException` is re-raised naming `s3vectors:ListVectors`
  and `s3vectors:GetVectors`.
- **Verified**: [`ListVectors`](https://docs.aws.amazon.com/AmazonS3/latest/API/API_S3VectorBuckets_ListVectors.html)
  exists with `maxResults` 1-1000 (default 500), `nextToken`, `returnData`, `returnMetadata`,
  `segmentCount`/`segmentIndex`; metadata needs `s3vectors:GetVectors` as well; it says nothing
  about order. The installed boto3 1.43.108 has `list_vectors` with those inputs and the response
  `{nextToken, vectors: [{key, data, metadata}]}`.
- **Order**: the service's order; a limit keeps the first N listed (spec FR-027).
- **Rejected**: parallel segments (spec: skipped); `get_paginator` (works, but the existing code
  loops by hand and the stub is simpler).

## R7. `Candidates` changes (backwards compatible)

- **Decision**: add one field at the end, `source: str = "seeds"`, so every existing positional
  construction (15 occurrences in tests and `candidates.py`) and every pre-feature file keeps
  working. For `"keywords"` and `"all"`: `floor` is `None`, `seeds_digest` and `embedding_model`
  are `None`. `read`/`write` carry `source` in the `.meta.json` (`meta.get("source", "seeds")`).
  `above`, `bands`, `top_seeds` and `evaluation.band_sample` call one small method that raises
  `ValueError` naming the source unless `source == "seeds"`. `__repr__`/`_repr_html_` branch on
  `source`: seeds unchanged; others print `N candidates (from keywords)` or `(whole corpus)`, and
  for keywords the table gets `terms_matched` and `matches` columns.
- **Rejected**: subclasses per source (abstraction for two flags); a `rank` column merging the two
  numbers (spec: two columns).

## R8. Default file output

- **Decision**: only a seeds result is written to the default location; keyword and whole-corpus
  results are written only when `out` is a path (spec FR-007). In code: `if out is not False and
  (out is not None or source == "seeds")`.
- **Why**: an unguarded `get_candidates(corpus)` would overwrite a paid seed result in
  `candidates.jsonl` and copy a whole corpus to disk (ponytail-review finding 1).

## R9. Scope of the rename and removal

Grep of the working tree (excluding `.venv` and `specs/001`-`006`, which stay as history):

- **Code**: `src/hunches/__init__.py` (exports), `candidates.py`, `search.py` (module docstrings
  and the `LocalCorpus` branch of `search_vectors`), `evaluation.py` (`band_sample`).
- **Tests mentioning `LocalCorpus`**: `test_corpus.py`, `test_search.py`, `test_search_pg_index.py`,
  `test_candidates.py`, `test_e2e.py`, `test_pre006_fixtures.py`, `test_public_api.py`,
  `test_pg_integration.py`. **Tests using `search`/`asearch`**: those plus `test_skills.py`,
  `test_docs.py`, `test_search_pg_*.py`, `tests/fixtures/pre006/README.md`. The `importlib.import_module("hunches.search")`
  workaround in the pg tests stays valid (the module is importable by name either way) and can be
  simplified later.
- **Wording that calls the library "already embedded"** (spec FR-019): `pyproject.toml` (the
  `description`), `src/hunches/__init__.py` (docstring), `plugin.json`,
  `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (two descriptions),
  `skills/hunches/SKILL.md` (description and first paragraph), `skills/hunches/references/workflow.md`
  ("The corpus is already embedded"), `README.md` (first paragraph and the agent block),
  `docs/agent-instructions.md`, `.kiro/steering/hunches.md`, `AGENTS.md` ("What this repo is").
  **`.specify/memory/constitution.md` line 3 says the same**; the constitution wins over
  `AGENTS.md` and only the user can amend it, so this is a gated task (see R12).
- **Docs**: `README.md` (and the block that must equal `docs/agent-instructions.md`),
  `AGENTS.md` (layout line, package quirk paragraph, "What this repo is"), `skills/hunches/SKILL.md`,
  `skills/hunches/references/workflow.md` (and the other references that show `hn.search`),
  `.kiro/steering/hunches.md` if it names them.
- **Example**: `examples/sample/README.md` (describes `corpus/`) changes with it.
  `examples/sample/corpus/{items.jsonl,vectors.npy,meta.json}` becomes
  `examples/sample/corpus.jsonl` (one JSON object per line: `id`, `text`, `embedding`), used as
  `hn.Table("corpus.jsonl", vector_column="embedding", embedding_model="hand-built-2d")`;
  `walkthrough.py` and `walkthrough.ipynb` change together (a test enforces they match).
- `tests/test_pre006_fixtures.py` reads `tests/fixtures/pre006/corpus` through `LocalCorpus` and
  `search_vectors`, and `test_corpus_is_well_formed` asserts the three-file layout
  (`meta.json`, `items.jsonl`, `vectors.npy` shape). Both tests are rewritten against a single
  `corpus.jsonl` and `search_table` (R11), with the same hand-computed numbers from
  `expected.json`; the pre-006 candidate, gold, cache and ledger files are untouched (they do not
  depend on the corpus format).

## R10. Package-name shadowing

`hunches.search` is currently the function (exported in `__init__`), hiding the submodule. Once
`search` is no longer exported the attribute is the submodule again; `hunches.cost` and
`hunches.settings` still shadow theirs. `AGENTS.md`'s quirk paragraph is rewritten to name only
those two. `tests/test_public_api.py` pins `__all__`; it is updated, not loosened.

## R11. Seed search over a `Table` reads the table once

- **Problem found in review**: `asearch` calls `search_vectors` once per seed, and the old local
  branch re-read `vectors.npy` and `items.jsonl` on every call. That was cheap for `.npy`; for a
  JSONL or CSV table with embeddings, every seed would re-parse and re-validate the whole file.
- **Decision**: a new `search_table(table, vectors, floor, embedding_model) -> (per_seed, capped)`
  in `search.py`, shaped like `search_pg_exact` (one pass for all seeds). It reads the table once,
  builds the float32 matrix once, normalises once, and does one matrix product for all seeds with
  the same cosine arithmetic as before (ties by earlier seed are decided later, in the unchanged
  merge loop). `capped` is always `False`. `get_candidates` calls it with a plain `if` for a
  `Table`, as it does for `search_pg_exact` today. The `LocalCorpus` branch of `search_vectors` is
  deleted; the function keeps its S3 and pgvector-index branches.
- **Rejected**: caching the parsed table on the `Table` object (hidden state, Principle V);
  keeping per-seed calls (the slowdown above).

## R12. Async form, and the constitution's description line

- **Blocking reads**: the new readers are blocking (file reads, `psycopg`, `boto3`). The async
  `aget_candidates` runs each whole read-and-match as a single `asyncio.to_thread(...)` call, as
  the pgvector exact branch already does (`candidates.py:203`), so the event loop is never blocked
  and no generator crosses a thread. Cancelling a running read is out of scope (no `Stop` handle,
  as the spec asks for none).
- **Constitution wording (amended, user-approved 2026-10-26, version 1.0.1)**: the constitution's opening sentence calls the library
  one "for content analysis over an already-embedded corpus". Spec FR-019 and FR-024 make that
  untrue. `AGENTS.md` may not disagree with the constitution, and amending it needs the user's
  approval through `/speckit-constitution` (a PATCH: wording only, no principle changes). The
  opening paragraph now reads "a corpus of items: candidates come from semantic search with seed
  phrases over embedded items, from keywords or regular expressions, or from the whole corpus".
  Done; `AGENTS.md` and the other wording sites (R9) are fixed in the documentation tasks.

## Open items carried to tasks (none block the design)

- Human checks on real services (spec Verification): server-side vs Python-side results on a real
  Postgres incl. the two-table layout; keyword read of a real S3 Vectors index; the Parquet
  paths with a real polars and with pandas+pyarrow.
- `uv sync --all-extras` pulls the heavy `local` extra and did not finish in 7 minutes here;
  development used `uv sync --extra s3 --extra pg --extra rds`, which is enough for every test in
  this plan (baseline: 450 passed, 17 skipped).

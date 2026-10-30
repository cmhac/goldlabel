# Feature Specification: Filter the corpus before candidates are drawn

**Feature Branch**: `claude/eager-ritchie-mvh7wf` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-10-30

**Status**: Draft, all questions resolved 2026-10-30 (ready for `/speckit-clarify` if wanted, else `/speckit-plan`)

**Input**: User description: "currently, goldlabel does not support filtering the corpus before keyword filters are applied. for example, we might want to apply a where clause on a postgres table to filter on some categorical column, THEN do keyword filters. Ideally, this would be applied on the corpus, before we call get_candidates. I would want this to work on all corpus types, not just postgres."

**Review decisions (user, 2026-10-30)**:

- Each corpus type gets its own filter, in the form that suits its backend. The classes are
  already separate, so the three forms do not need to match.
- `Table` reads and filters with polars only. A pandas DataFrame is still accepted and is
  converted with `polars.from_pandas`. Files are read only by polars. This removes the current
  mix (the standard library for CSV and JSONL, polars or else pandas for Parquet, `to_dicts` or
  `to_dict` for frames), so there is one reading path and one filtering method.
- A `Table` filter is a polars expression (`pl.col("section") == "politics"`), applied with
  `DataFrame.filter`. (A row function applied with `map_elements` was considered and dropped:
  it runs Python once per row, the slowness the user wanted to avoid.)
- In the Postgres two-table layout (`text_table`), the filter columns must be in the text table,
  and the docs say so plainly.
- A `PgCorpus` filter is one SQL condition string with its values written into it
  (`"section = 'politics'"`). There is no separate parameters argument.
- An `S3Corpus` filter is the service's own metadata filter document, applied by the library
  itself when listing.
- polars and pyarrow become core dependencies of goldlabel.
- The agent skills must teach agents how each corpus's filter works so they can help a user who
  does not know polars expressions, Postgres SQL or the S3 filter language write one.

## Context

Today a corpus is "every item in the source". `get_candidates` then applies at most one filter
(seeds or keywords) to all of it. This feature adds a filter that lives on the corpus object.
Every way `get_candidates` reads a filtered corpus (whole corpus, keywords, seeds) then sees only
the items that pass. The filter is a statement about the corpus ("the politics section of this
table"), not a fourth candidate filter.

Facts this spec relies on (checked 2026-10-30):

- **polars**: `map_elements` runs the function once per row in Python. The polars docs call it
  strongly discouraged next to native expressions, which run in Rust, in parallel and optimised
  ([Expr.map_elements](https://docs.pola.rs/api/python/dev/reference/expressions/api/polars.Expr.map_elements.html)).
  This is why the Table filter is an expression.
  - `polars.from_pandas` requires pyarrow
    ([from_pandas](https://docs.pola.rs/py-polars/html/reference/api/polars.from_pandas.html)).
  - Checked on the installed polars 2.1.0: `read_csv` infers types by default, which turns the
    id `"007"` into the number `7`. `infer_schema=False` keeps every value as text, as the
    current CSV reader does.
- **S3 Vectors**: `QueryVectors` takes a metadata `filter` document. Its operators are `$eq`
  (also the meaning of a bare value; on a list value it matches any element), `$ne`, `$gt`,
  `$gte`, `$lt`, `$lte`, `$startsWith` (ENHANCED query behaviour only), `$in`, `$nin`, `$exists`,
  `$and` and `$or`.
  - On CLASSIC indexes, a filtered query may return fewer than topK hits.
  - `ListVectors` has no filter parameter. Metadata the index declared non-filterable cannot be
    used in a filter, but it is still returned
    ([metadata filtering](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-metadata-filtering.html),
    [ListVectors](https://docs.aws.amazon.com/AmazonS3/latest/API/API_S3VectorBuckets_ListVectors.md)).
  - The docs do not say how a vector without the key is treated by `$ne` and `$nin`, or how
    `$in` treats a list value.
- **psycopg** (checked on the installed 3.3.6): when a query is sent with parameters, a literal
  `%` in its text must be written `%%`, or the driver refuses it ("only '%s', '%b', '%t' are
  allowed as placeholders"). With an empty parameter tuple, `%%` becomes `%`; with no parameters
  at all, `%%` is sent as it is. So the library can double every `%` in the user's condition and
  always send parameters, and the user writes plain SQL (`LIKE 'vote%'`).
- **pgvector**: a `WHERE` is applied after the HNSW index scan. Iterative scans (0.8.0+, already
  on in index mode) keep scanning up to `hnsw.max_scan_tuples`, so a filtered index search can
  still return fewer hits than an exact one
  ([pgvector 0.8.0 README](https://pgxn.org/dist/vector/0.8.0/README.html)).

## Filter forms

### Table (decided)

```python
import polars as pl

corpus = gl.Table(
    "articles.parquet",
    id_column="id",
    where=(pl.col("section") == "politics") & (pl.col("year") >= 2024),
)
```

- `where` is one polars expression, over the source's own column names, that evaluates to a
  boolean per row. It is applied with `DataFrame.filter`, before the existing row checks, so a row
  that is filtered out cannot fail the read (for example, by having an empty text).
- A CSV is read with every value as text, so a number has to be cast:
  `pl.col("year").cast(pl.Int64) >= 2024`. The docs and the skills say so.
- A row where the expression is null (for example, a missing value compared with `==`) is
  dropped, which is what `DataFrame.filter` does; the docs say so.
- Anything that is not a `pl.Expr` is refused when the `Table` is built. An expression polars
  cannot evaluate on the source (a column it does not have, a type mismatch) fails on reading
  with polars' own message, prefixed to say it came from the filter.

### PgCorpus (decided)

```python
corpus = gl.PgCorpus(
    "articles",
    where="section = 'politics' AND published >= '2024-01-01'",
)
```

- `where` is one SQL condition, in Postgres syntax, with its values written into it. Any
  operator, function or column of the table can be used. A quote inside a value is doubled, as
  in any SQL (`'O''Brien'`), and a `%` is written once (`LIKE 'vote%'`); the library handles the
  driver's `%` rule (see Context).
- The condition runs inside the existing read-only transaction, so it cannot change data, and the
  library sends every query with parameters, which the server runs as a single statement.
- The SQL text is code the user wrote in their own notebook against their own database. The
  library passes it through unchanged and does not try to validate it.
- The library puts the condition in a CTE (`WITH goldlabel_where AS (SELECT id FROM <table>
  WHERE (<condition>))`) and keeps rows whose id is in it. `<table>` is the text table in the
  two-table layout and the table otherwise. A CTE cannot see the main query's tables, so a column
  name always means a column of that one table, never one of the search's own helper columns or
  the vector table's. (A plain sub-query would quietly fall back to the outer query's columns.)
- Two-table layout: a column that is only in the vector table gives the database's own "column
  does not exist" error, with a line added saying that filter columns must be in the text table.

### S3Corpus (decided)

```python
corpus = gl.S3Corpus(
    "my-bucket",
    "articles",
    where={"$and": [{"section": "politics"}, {"year": {"$gte": 2024}}]},
)
```

- `where` is the service's own filter document, sent unchanged as `filter` on every similarity
  query.
- Listing has no filter, so for the whole corpus and keywords the library evaluates the same
  document on each listed vector's metadata. It supports every documented operator except
  `$startsWith`, which is refused for listing because its availability depends on the index
  mode.
- Where the AWS docs are silent, the library's rules are written down and tested:
  - A vector without the key fails every operator except `$exists: false` and `$ne`/`$nin`,
    which it passes.
  - `$in` on a list value matches if any element is in the list, as `$eq` does.
  - Both rules are marked as unverified against the service (manual check, below).

### Agent skills (decided)

The user's request is often in plain words ("only the politics section since 2024"). The skills
must let an agent turn that into the right filter for the corpus in use, with the user deciding
what the filter is:

- `goldlabel-connect` (where the corpus is built) gets a short section per corpus type: the form,
  two or three worked examples (one value, one of several values, a date or number range), and
  that type's pitfalls (CSV values are text; Postgres quotes and the text-table rule; S3
  filterable keys, the missing-key and list rules, no `$startsWith` when listing).
- The agent first looks up the real column or metadata names and their values (the Table's
  schema and a few rows; for Postgres, the columns the user or a schema query of theirs shows; a few listed S3
  vectors' metadata) instead of guessing them.
- The agent shows the filter it wrote, explains it in plain words, and asks the user to confirm it
  before using it. It then suggests a quick check, `get_candidates(corpus, limit=20)`, so the user
  can see that the right items come back.
- The agent never chooses a filter, a column or a value on its own.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Keywords inside one category of a Postgres table (Priority: P1)

A user with a large Postgres table of articles wants the keyword candidates from the `politics`
section only. They say so once on the corpus, then call `get_candidates(corpus, keywords=[...])`
exactly as today. Rows outside the section never leave the server.

**Why this priority**: it is the case that prompted the request, and the one where filtering in
Python afterwards is not an option, because the table may not fit in memory.

**Independent Test**: using the fake `psycopg`, build a filtered corpus and ask for keywords with
and without `server_side`. Check that the condition is in the SQL sent, exactly once, and that
only the filtered rows come back.

**Acceptance Scenarios**:

1. **Given** a table where rows 1-3 are `politics` and rows 4-5 are `sports`, and rows 2 and 4
   contain "ballot", **When** the user filters to `section = politics` and asks for the keyword
   "ballot", **Then** the result holds only row 2.
2. **Given** the same corpus and no keywords, **When** the user asks for the whole corpus,
   **Then** the result holds rows 1-3 in id order.
3. **Given** a two-table layout whose `section` column is in the text table, **When** the user
   filters on it, **Then** the right rows come back, in every mode.
4. **Given** a two-table layout and a filter on a column that is only in the vector table,
   **When** the search runs, **Then** it fails with the database's error, and the message adds
   that filter columns must be in the text table.
5. **Given** a filter that no row passes, **When** the search runs, **Then** the result is empty
   and says so in words (0 candidates), not an error.
6. **Given** a condition with a `%` in a `LIKE` pattern and a doubled quote in a value,
   **When** the search runs in each mode (whole corpus, server-side keywords, exact seeds),
   **Then** the database receives the condition exactly as the user wrote it.

---

### User Story 2 - The same need on a Table (Priority: P1)

The same user works from a Parquet, CSV or JSONL file, a polars or pandas DataFrame, or a list of
rows. They pass a polars expression and get the same behaviour.

**Why this priority**: the user asked for every corpus type, and `Table` is the default corpus.

**Independent Test**: build one tiny dataset as every source type and apply the same expression.
Check the exact ids against a hand-written expectation for each source.

**Acceptance Scenarios**:

1. **Given** a `Table` whose rows carry a `section` column and the expression
   `pl.col("section") == "politics"`, **When** the user asks for the whole corpus, keywords or
   seeds, **Then** only those rows are candidates.
2. **Given** something that is not a polars expression (a string, a function), **When** the
   `Table` is built, **Then** it is refused with a message that shows the expression form.
3. **Given** an expression on a column the source does not have, **When** the corpus is read,
   **Then** the error says it came from the filter and keeps polars' own message.
4. **Given** a CSV with a `year` column and `pl.col("year").cast(pl.Int64) >= 2024`, **When** the
   corpus is read, **Then** the rows from 2024 on are kept.

---

### User Story 3 - The same need on S3 Vectors (Priority: P2)

**Acceptance Scenarios**:

1. **Given** an S3 index whose vectors carry `section` metadata, **When** the corpus is filtered
   and the whole corpus or keywords are asked for, **Then** only vectors whose metadata passes
   are kept.
2. **Given** the same corpus and seeds, **When** the search runs, **Then** the filter is sent
   with every similarity query, so hits outside it never come back and do not use up topK.
3. **Given** a filter document that is not a dict, or uses an unknown operator, **When** the
   corpus is built, **Then** it is refused with a message naming the problem.

---

### User Story 4 - Seed search over a filtered corpus (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a filtered `Table`, `PgCorpus` (exact and index search) or `S3Corpus`, **When** the
   user runs seed search, **Then** no candidate falls outside the filter.
2. **Given** a filtered `PgCorpus` in index search, **When** the result is shown, **Then** it
   carries the existing approximate-search warning.

---

### User Story 5 - An agent helps a user write a filter (Priority: P2)

A user who does not know polars, SQL or the S3 filter language asks their agent for "only the
politics section since 2024". The agent looks up the real column names and values, writes the
filter for the corpus in use, explains it and asks before using it.

**Independent Test**: the drift tests run every code block in the skills against the real public
names; a manual trial in an agent (as for 009) checks the behaviour.

**Acceptance Scenarios**:

1. **Given** each corpus type, **When** an agent reads `goldlabel-connect`, **Then** it finds the
   filter form, worked examples and that type's pitfalls.
2. **Given** a plain-words request, **When** the agent writes a filter, **Then** it uses names it
   looked up, shows the filter, explains it in plain words and waits for the user's yes.

---

### User Story 6 - Nothing else changes (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a corpus built without a filter, **When** any existing call runs, **Then** the
   result, the queries sent and the ids are identical to today's. That includes CSV ids such as
   `"007"`, and JSONL and Parquet values.
2. **Given** an existing test of `Table` reading, **When** the polars-only reader replaces the
   current one, **Then** the test passes unedited, or the plan names each edit and why (for
   example, an error message whose wording changes).

### Edge Cases

- A CSV value is always text, also inside the filter expression. The docs say so.
- JSONL rows with missing keys: polars fills them with null. The existing "no column" error must
  still fire for the text and id columns, not turn into a null-text error with a different
  message.
- A JSONL or list-of-rows source whose values change type between rows: if polars cannot build
  one column type, the error names the column.
- Postgres up-front "result too large" refusal: it uses whole-table statistics, which overstate a
  filtered read. With a filter it is skipped, and the streaming size check still applies.
- A Postgres `where` that is not a string, or is blank: refused when the corpus is built.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `Table`, `PgCorpus` and `S3Corpus` MUST each accept an optional filter when they
  are built, in the forms above. Without one, each behaves exactly as today.
- **FR-002**: Every way `get_candidates` reads a filtered corpus MUST see only the items that
  pass. That covers the whole corpus, keywords in Python, keywords on the server, and seed search
  in every mode.
- **FR-003**: `Table` MUST read every source with polars only:
  - Files with `read_csv` (every value as text), `read_ndjson` and `read_parquet`.
  - Polars DataFrames as they are.
  - pandas DataFrames through `polars.from_pandas`.
  - Lists of rows through `polars.DataFrame`.
  - Nothing in `Table` reading may use pandas, the `csv` module or `json` line parsing.
- **FR-004**: `Table` MUST apply the filter expression with `DataFrame.filter`, then run the
  existing row checks and produce the same `{id, text[, vector]}` rows as today.
- **FR-005**: polars and pyarrow MUST become core dependencies of goldlabel. Importing
  `goldlabel` MUST still not import polars (constitution VII); polars is imported when a `Table`
  is read or a filter is checked. pandas stays optional, needed only for `.to_pandas()` and for
  passing a pandas DataFrame. Result exports keep both `.to_polars()` and `.to_pandas()`.
  The constitution and `AGENTS.md` lines that call polars a dev-only dependency MUST be updated
  in the same change.
- **FR-006**: On Postgres, the filter MUST run in the database, inside the existing read-only
  transaction, exactly as the user wrote it (the library doubles `%` and always sends
  parameters, see Context). In the two-table layout it MUST be evaluated against the text table
  only.
- **FR-007**: On S3 Vectors, similarity queries MUST send the filter document unchanged. Listing
  MUST evaluate the same document on the returned metadata, by the rules above.
- **FR-008**: A malformed filter MUST be refused when the corpus is built, with a message naming
  the problem. Examples: a Table filter that is not a polars expression, a Postgres `where` that
  is not a string or is blank, an S3 document with an unknown operator.
- **FR-009**: A corpus's plain `repr` MUST show its filter as given (the expression, the SQL
  text, the S3 document). Nothing new is written to `candidates.jsonl` or its `.meta.json`.
- **FR-010**: The README MUST show each backend's filter once. `goldlabel-connect` MUST carry the
  per-corpus guidance in "Agent skills" above, and `goldlabel-candidates` MUST remind the agent
  that the filter is on the corpus. Every code block uses real names that the drift tests check.
  Both MUST say that Postgres filter columns must be in the text table in the two-table layout.
- **FR-011**: Whether to filter, and on what, is the user's decision. The skills MUST tell agents
  to look up real column names and values, show and explain the filter they wrote, and wait for
  the user's yes; never to choose a filter, column or value themselves.

### Key Entities

- **Corpus filter**: an optional, immutable part of a corpus.
  - Table: a polars expression that is a boolean per row.
  - Postgres: one SQL condition string with its values written in.
  - S3 Vectors: a metadata filter document.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each backend, a filtered corpus gives exactly the hand-written expected ids in
  every mode: whole corpus, keywords and seeds.
- **SC-002**: On Postgres, no row outside the filter is received by the client in any mode,
  checked by what the fake driver returns for the SQL it is sent.
- **SC-003**: `Table` reads every source type through one polars path. A search of the source
  for `pandas`, `csv.` and line-by-line `json` parsing in Table reading finds none.
- **SC-005**: For each corpus type, the skill's worked examples run unchanged against a tiny
  fixture of that type (the drift tests).
- **SC-004**: Every existing test passes, apart from the edits the plan names under User Story 5.

## Assumptions

- Postgres needs an index on a filtered column to be fast. The library does not create one.
- S3 metadata keys used in a similarity-query filter are filterable. If one is not, the
  service's error is shown as it is.
- Candidate files do not record the filter, because the notebook is the record (Principle V).
- Manual checks a human must do, which tests cannot: the agent trial in User Story 5; a filtered keyword, whole-corpus and seed
  search against a real Postgres (single and two-table), and against a real S3 Vectors index,
  including the missing-key and list-value rules.

## Deliberately skipped *(Ponytail)*

- A Python row function for the Table filter (`map_elements`): slow, and dropped by the user.
- A separate parameters argument for the Postgres filter: values are written into the SQL.
- Checking, parsing or rewriting the user's SQL condition.
- Filtering at `get_candidates` time instead of on the corpus, because the request puts it on the
  corpus.
- One filter form shared by all backends, because the user chose per-backend forms.
- Recording the filter in `candidates.jsonl`, `.meta.json` or the evaluation log.
- Counting how many items pass a filter before searching.
- Creating indexes, or checking that a filtered Postgres column is indexed (`PgCorpus.check` is
  unchanged).
- `$startsWith` when listing S3 vectors.
- Lazy or streaming polars reads (`scan_*`) for tables larger than memory: `Table` already reads
  the whole source today.

# Feature Specification: Filter the corpus before candidates are drawn

**Feature Branch**: `claude/eager-ritchie-mvh7wf` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-10-30

**Status**: Draft, 2 questions open (marked `[NEEDS CLARIFICATION]`)

**Input**: User description: "currently, goldlabel does not support filtering the corpus before keyword filters are applied. for example, we might want to apply a where clause on a postgres table to filter on some categorical column, THEN do keyword filters. Ideally, this would be applied on the corpus, before we call get_candidates. I would want this to work on all corpus types, not just postgres."

## Context

Today a corpus (`Table`, `S3Corpus`, `PgCorpus`) is "every item in the source". `get_candidates`
then applies at most one filter (seeds or keywords) to all of it. A user who only cares about one
section, one outlet or one year has no way to say so on a Postgres table or an S3 Vectors index; on
a `Table` they can filter the DataFrame themselves first, but not a file path, and the result is a
different idiom per backend.

This feature adds one restriction that lives on the corpus object, so the same `get_candidates`
call (whole corpus, keywords or seeds) sees only the items that pass it. The restriction is
metadata about the corpus ("the politics section of this table"), not a fourth candidate filter.

Facts this spec relies on (checked 2026-10-30): S3 Vectors `QueryVectors` accepts a metadata
`filter` (bare value = `$eq`, plus `$in`, `$and` and others; all metadata is filterable unless the
index declared a key non-filterable) and may return fewer than topK hits when few vectors match;
`ListVectors` has no filter, so listing must filter the returned metadata itself. pgvector applies
a `WHERE` after the HNSW index scan; iterative scans (0.8.0+, already turned on in index mode) keep
scanning up to `hnsw.max_scan_tuples`, so a filtered index search can still return fewer hits than
an exact one.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Keywords inside one category of a Postgres table (Priority: P1)

A user with a large Postgres table of articles wants the keyword candidates from the `politics`
section only. They say so once on the corpus, then call `get_candidates(corpus, keywords=[...])`
exactly as today. Rows outside the section never leave the server.

**Why this priority**: it is the case that prompted the request, and the one where filtering in
Python afterwards is not an option (the table may not fit in memory).

**Independent Test**: with the fake `psycopg`, build a corpus restricted to `section = politics`,
ask for keywords with and without `server_side`, and check the SQL sent carries the restriction as
a bound parameter and that only the restricted rows come back.

**Acceptance Scenarios**:

1. **Given** a table where rows 1-3 are `politics` and rows 4-5 are `sports`, and rows 2 and 4
   contain "ballot", **When** the user restricts the corpus to `section = politics` and asks for
   the keyword "ballot", **Then** the result holds only row 2.
2. **Given** the same corpus and no keywords, **When** the user asks for the whole corpus,
   **Then** the result holds rows 1-3 in id order.
3. **Given** a restriction to "one of" two values (`politics` or `opinion`), **When** the search
   runs, **Then** a row in either value is kept.
4. **Given** a restriction on two columns (`section = politics` and `outlet = post`), **When** the
   search runs, **Then** a row is kept only if it passes both.
5. **Given** a restriction value that contains a quote, a semicolon or SQL text, **When** the
   search runs, **Then** it is compared as a plain value and never becomes part of the query
   text; a column name is always quoted as a name.
6. **Given** a restriction that no row passes, **When** the search runs, **Then** the result is
   empty and says so in words (0 candidates), not an error.

---

### User Story 2 - The same restriction on a Table and on S3 Vectors (Priority: P1)

The same user, working from a Parquet export or an S3 Vectors index, writes the same restriction
in the same form and gets the same behaviour.

**Why this priority**: the user asked for every corpus type; one form for all three is the point.

**Independent Test**: on a tiny hand-built `Table` (file and DataFrame) and a stubbed S3 client,
apply the restrictions from story 1 and check the exact ids against a hand-written expectation.

**Acceptance Scenarios**:

1. **Given** a `Table` whose rows carry a `section` column, **When** it is restricted to
   `section = politics`, **Then** whole-corpus, keyword and seed candidates hold only those rows.
2. **Given** a `Table` restricted on a column it does not have, **When** it is read, **Then** the
   call fails with a message that names the column and the first row without it.
3. **Given** an S3 Vectors index whose vectors carry `section` metadata, **When** it is restricted
   and the whole corpus or keywords are asked for, **Then** only vectors whose metadata passes are
   kept (filtered after listing, since listing has no filter).
4. **Given** the same S3 corpus and seeds, **When** the search runs, **Then** the restriction is
   sent with every similarity query, so hits outside it never come back and do not use up topK.
5. **Given** an S3 vector with no value for a restricted key, **When** the corpus is read,
   **Then** that vector is left out (it does not pass), as the service's own filter does.

---

### User Story 3 - Seed search over a restricted corpus (Priority: P2)

A user restricts the corpus and then runs seed search; the similarity hits come only from the
restricted items.

**Why this priority**: "the restriction is on the corpus" means every way of reading the corpus
honours it. Leaving seed search out would make the same corpus object mean two things.

**Independent Test**: restrict a `Table` with hand-built vectors where the best match for a seed
is outside the restriction; check that the result's best row is the best one inside it.

**Acceptance Scenarios**:

1. **Given** a restricted `Table`, `PgCorpus` (exact and index search) or `S3Corpus`, **When** the
   user runs seed search, **Then** no candidate falls outside the restriction.
2. **Given** a restricted `PgCorpus` in index search, **When** the result is shown, **Then** it
   carries the existing approximate-search warning, because a filtered index scan can miss hits.

---

### User Story 4 - Nothing changes for an unrestricted corpus (Priority: P1)

Every existing notebook, corpus and saved candidate file behaves exactly as before.

**Acceptance Scenarios**:

1. **Given** a corpus built without a restriction, **When** any existing call runs, **Then** the
   result and the queries sent are identical to today's; the existing tests pass unchanged.

### Edge Cases

- A `Table` from a CSV holds every value as text: a restriction to the number `2024` does not
  match the text `"2024"`. Values are compared as the source holds them, and the docs say so.
- An empty restriction (no columns), an empty "one of" list, or a blank column name is refused
  when the corpus is built.
- A missing value (`None`) as a restriction value is refused when the corpus is built.
- A Postgres column that does not exist: the database's own error, scrubbed as today.
- With a restriction, the Postgres up-front "result too large" refusal for the whole corpus uses
  whole-table statistics, which overstate a filtered read; it is skipped when a restriction is set,
  and the streaming size check still applies.
- A restriction on the Postgres two-table layout: see FR-007.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each corpus type (`Table`, `S3Corpus`, `PgCorpus`) MUST accept an optional
  restriction when it is built; without one it behaves exactly as today.
- **FR-002**: The restriction MUST have the same form for all three corpus types:
  [NEEDS CLARIFICATION: which form? Recommended: a mapping of column name to one value (equal to)
  or a list of values (one of), all columns ANDed, e.g. `where={"section": "politics", "outlet":
  ["post", "wire"]}`. Alternatives: the same plus a Postgres-only raw SQL string; or each backend's
  native form (SQL text, S3 filter document, a Python callable for a Table).]
- **FR-003**: Every way `get_candidates` reads a restricted corpus (whole corpus, keywords
  in Python, keywords on the server, seed search in every mode) MUST see only the items that pass.
- **FR-004**: On Postgres the restriction MUST run in the database, with column names quoted as
  identifiers and values sent only as bound parameters, inside the existing read-only transaction.
- **FR-005**: On S3 Vectors similarity queries MUST send the restriction as the service's metadata
  filter; listing MUST apply the same rule to the returned metadata.
- **FR-006**: On a `Table` the restriction MUST be applied to the rows as read, before any other
  check that would refuse a row outside it (a row outside the restriction with an empty text does
  not fail the read).
- **FR-007**: On a Postgres two-table layout (`text_table`) the restricted columns MUST be looked
  up in [NEEDS CLARIFICATION: which table? Recommended: the text table, where article fields
  usually live next to the text. Alternatives: the vector table; or either, chosen per column.]
- **FR-008**: A restriction MUST be checked when the corpus is built (empty mapping, blank or
  non-string column name, empty list, `None` value) and refused with a message naming the problem.
- **FR-009**: The restriction MUST be part of the corpus's plain `repr` so a notebook shows what
  was read; nothing new is written to `candidates.jsonl` or its `.meta.json`.
- **FR-010**: The agent skills (`goldlabel-connect`, `goldlabel-candidates`) and the README MUST
  show the restriction once, using real names (the drift tests check them).
- **FR-011**: Whether to restrict and to what is the user's decision; the skills MUST tell agents
  to ask, never to pick a restriction themselves.

### Key Entities

- **Restriction**: an optional, immutable part of a corpus: the columns (Postgres), keys (S3
  metadata) or fields (Table rows) an item must match, with the value or values each may take.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: One restriction written once runs unchanged on all three corpus types and gives the
  same ids on the same data (checked on one hand-built dataset loaded into each).
- **SC-002**: On Postgres, no row outside the restriction is received by the client in any mode
  (checked by what the fake driver returns for the SQL it is sent).
- **SC-003**: No restriction value ever appears in the text of a query sent to Postgres.
- **SC-004**: Every existing test passes without being edited.

## Assumptions

- The restriction is about equality on categorical values, as in the request; ranges and other
  comparisons are out of scope (see below) unless FR-002 is answered otherwise.
- The S3 metadata keys used in a restriction are filterable; if a key was declared non-filterable,
  the service's error is shown as is.
- Postgres needs an index on a restricted column to be fast; the library does not create one.
- Candidate files do not record the restriction: the notebook is the record (Principle V).

## Deliberately skipped *(Ponytail)*

- Ranges, "not equal", "not in", `IS NULL`, `LIKE`, OR across columns, nested logic.
- A raw SQL `where` string for Postgres (unless chosen for FR-002).
- A Python callable or polars/pandas expression as the restriction for a `Table`: filter the
  DataFrame before building the `Table`.
- Restricting at `get_candidates` time instead of on the corpus (the request puts it on the corpus).
- Recording the restriction in `candidates.jsonl` / `.meta.json`, or in the evaluation log.
- Counting how many items pass a restriction before searching.
- Creating indexes or checking that a restricted column is indexed (`PgCorpus.check` unchanged).
- Coercing types (text `"2024"` vs number `2024`) between the restriction and the source.

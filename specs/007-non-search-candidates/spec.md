# Feature Specification: Non-search candidate sources

**Feature Branch**: `ccr-26b50054-jcevqw` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-10-26

**Status**: Draft (revised 2026-10-26 after review: regex flags, ranked keyword hits, a limit argument, server-side SQL filtering)

**Input**: User description: "Non-search candidate sources for the hunches library: let a user build a Candidates list without semantic seed search. (1) a keyword/regex candidate list over a corpus, and (2) the whole corpus with no filtering. Today `Candidates` rows assume `max_similarity` and `best_seed`, so its repr, bands, above, top_seeds and band_sample break on rows without them; the corpus classes (LocalCorpus, S3Corpus, PgCorpus) have no plain item reader, only the search code reads items. Proposed shape (to be refined in the spec): make similarity fields optional on Candidates with plain-count fallbacks in repr/_repr_html_, record a `source` ("seeds", "keywords", "all"), and add `hn.keywords(corpus, terms, regex=False)` and `hn.everything(corpus)` with a streaming item reader for all three corpus types (pgvector tables can be larger than memory). Must keep: no I/O on import, async+sync forms, polars+pandas export, unknown cost shown as `?`, never touch gold labels, minimal implementation with no abstractions."

**Review decisions (user, 2026-10-26)**: `LocalCorpus` is removed, because its folder layout (`vectors.npy` + `items.jsonl` + `meta.json`) was this tool's own invention while Postgres, S3 Vectors and tabular files are existing standards; `Table` replaces it, and a table needs an embedding column only when the user wants seed search; a corpus with no embeddings is a valid input when no semantic search is used; data may come from a CSV, Parquet or JSONL file, a pandas or polars DataFrame, or a list of rows, for semantic search too when the rows already carry embeddings (story 6);  several regular expressions with their own flags, each searched separately; keyword hits ranked the way semantic hits are; a `limit` argument defaulting to no limit; one corpus per call, with merging corpora left to the user upstream and no source registry or system-wide storage; and server-side SQL filtering for Postgres as a real feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Classify the whole corpus, no filtering (Priority: P1)

A user whose corpus is small enough, or whose question is "label everything", wants every item in
the corpus as a candidate list without writing seed phrases or choosing a similarity cutoff. The
result behaves like any other candidate list: it shows how many items it holds, can be sampled for
the labelling page, and can be handed to the classifier.

**Why this priority**: it is the simplest case and the one with the least new behaviour: no
matching logic, only a way to read a corpus's items and a candidate list that does not pretend its
items have a similarity or a rank. Everything in the later stories needs the same two pieces.

**Independent Test**: build a candidate list from a tiny table with no seeds and no
embedder, check it holds every item exactly once, draw gold rows from it, and estimate a
classification of it, all without any model call.

**Acceptance Scenarios**:

1. **Given** a corpus of five items, **When** the user asks for the whole corpus, **Then** the
   result holds five candidates, each with its `id` and `text`, in the corpus's own order.
2. **Given** that result, **When** it is shown, **Then** the text says it holds five candidates
   and that it came from the whole corpus; it shows no similarity bands, no similarity column, no
   seed column and no rank.
3. **Given** that result, **When** the user draws gold rows from it and estimates a classification
   of it, **Then** both work exactly as they do for a seed-search result.
4. **Given** that result, **When** the user asks for the items above a similarity cutoff, for
   the top seeds, or for a per-band sample, **Then** the call fails at once with a message that
   says this list has no similarity because it was not built from seeds.
5. **Given** a corpus of five items and a limit of two, **When** the user asks for the whole
   corpus, **Then** the result holds the first two items in the corpus's order.

---

### User Story 2 - A ranked keyword and regex candidate list (Priority: P2)

A user who already knows words or patterns that mark the items they care about (a name, a phrase,
a hashtag) wants the items that match them, best first, without embedding anything and without
paying for an embedding call. Terms can be plain text or regular expressions, and each regular
expression can carry its own flags.

**Why this priority**: it is the most common "simple filter" and the reason the question was asked,
but it needs story 1's reader and list first.

**Independent Test**: on a tiny table, ask for plain terms, then for several regular
expressions with different flags, and check the exact ids and their order against a hand-written
expectation.

**Acceptance Scenarios**:

1. **Given** a corpus where items 2 and 4 contain "ballot", **When** the user asks for the keyword
   "ballot", **Then** the result holds exactly items 2 and 4, whatever their case ("Ballot",
   "BALLOT").
2. **Given** two terms, **When** the user asks for items matching them, **Then** an item that
   matches either term is included once.
3. **Given** the same text passed as a plain string with the regex option off and with it on,
   **When** the search runs, **Then** it is matched as literal text in the first case and as a
   pattern in the second.
4. **Given** three regular expressions, one case-insensitive, one case-sensitive and one with the
   dot matching line breaks, **When** the search runs, **Then** each is applied to every item with
   its own flags, independently of the others, so one expression's flags never change how another
   matches.
5. **Given** items that match different numbers of the terms, **When** the result is shown,
   **Then** the items are in rank order, best first, with ties kept in corpus order, and each row
   carries the value it was ranked by. *(The ranking rule is the first open question below.)*
6. **Given** a limit of three and ten matching items, **When** the search runs, **Then** the result
   holds the three best-ranked items; with no limit it holds all ten.
7. **Given** a term that matches nothing, **When** the search runs, **Then** the result is empty
   and says so in words (0 candidates), not an error.
8. **Given** an invalid regular expression, **When** the user asks for it, **Then** the call fails
   before reading the corpus, with a message that names the pattern.
9. **Given** the result, **When** it is shown, **Then** it says it came from keywords, gives the
   count and the rank column, and shows no similarity bands.

---

### User Story 3 - Existing searches and saved files are unchanged (Priority: P1)

A user with a seed-search result, a `candidates.jsonl` written by an earlier version, or a
notebook using the band report must see exactly what they saw before. Semantic search keeps its
ranking: best similarity first, ties by id.

**Why this priority**: the change widens a type that every later stage uses. Breaking existing
results or files would cost more than the feature gives.

**Independent Test**: the existing candidate, gold, evaluation and pre-006 fixture tests pass
unchanged, and a file written before this feature loads as a seed-search result.

**Acceptance Scenarios**:

1. **Given** a `candidates.jsonl` and `.meta.json` with no record of a source, **When** it is read,
   **Then** it is a seed-search result and shows its bands as before.
2. **Given** a seed-search result, **When** it is written and read back, **Then** it is equal to the
   original and still says it came from seeds.
3. **Given** a keyword or whole-corpus result, **When** it is written and read back, **Then** it
   keeps its source and its rank values and shows no bands.

---

### User Story 4 - Filter on the database server for a big Postgres table (Priority: P3)

A user whose corpus is a large Postgres table (with or without an embedding column) wants the database to do the keyword or regular
expression filtering, so that only matching rows leave the server, instead of every row being
downloaded and matched in Python.

**Why this priority**: it is an optimisation of story 2 for one backend, valuable on large tables,
and it cannot be verified against a real database from the test suite.

**Independent Test**: with the fake database, a keyword search with server-side filtering sends a
read-only query that contains the user's terms as parameters (never spliced into the SQL text) and
returns the rows the fake answers with, ranked and limited like a Python-side search.

**Acceptance Scenarios**:

1. **Given** a Postgres corpus and the server-side option, **When** a keyword search runs, **Then**
   one read-only statement per search is sent, only matching rows are received, and the terms
   reach the database as bound parameters.
2. **Given** a user term containing `%`, `_`, quotes or `;`, **When** the search runs with literal
   matching, **Then** it is matched as the literal characters and cannot alter the statement.
3. **Given** a corpus that is not a Postgres corpus, **When** the server-side option is asked for,
   **Then** the call fails with a message saying only a Postgres corpus can filter on the server.
6. **Given** a Postgres table with only an id column and a text column (no embedding column, no
   vector extension installed), **When** a keyword search or a whole-corpus request runs, **Then**
   it works; a seed search against the same table fails with a message that says the table has no
   embedding column to search.
4. **Given** a regular expression with flags that the database's regular-expression language
   cannot express, **When** the server-side option is on, **Then** the call refuses and names the
   flag instead of silently matching differently. *(The flag mapping is the second open question.)*
5. **Given** the same corpus read both ways, **When** the terms are plain text, **Then** the
   server-side and the Python-side searches return the same ids in the same order.

---

### User Story 5 - Big remote corpora do not need to fit in memory to be keyword-searched (Priority: P3)

A user with a corpus in a Postgres table or an S3 Vectors index, larger than memory, wants a
keyword list from it. Only the matching items, or only the best `limit` of them, are kept.

**Why this priority**: a table covers the main need; the read-only remote readers are the
same feature on bigger data and cannot be verified without a real database or bucket.

**Independent Test**: with the fake database and a stubbed S3 client, a Python-side keyword search
over many times more rows than one batch returns the right matches, issues no write, and never
holds more than one batch of unmatched items plus the kept matches.

**Acceptance Scenarios**:

1. **Given** a Postgres or S3 corpus, **When** a keyword search runs without the server-side
   option, **Then** every item is read once, only matches are kept, and nothing is written to the
   database or the bucket.
2. **Given** a limit of N, **When** a keyword search runs, **Then** the library never holds more
   than N ranked matches at a time.
3. **Given** a Postgres corpus and a request for the whole corpus, **When** the table is larger than
   the corpus's own result-size limit, **Then** the call refuses with a message that names the
   limit instead of exhausting memory.

---

### User Story 6 - Bring your own table: CSV, Parquet, JSONL, DataFrame (Priority: P1)

A user whose data is in a CSV or Parquet file, or already in a pandas or polars DataFrame, wants to
build candidates from it directly, without first writing a folder of `items.jsonl`. They say which
column is the id (optional) and which is the text. If the table also has an embedding column, the
same table works for seed search.

**Why this priority**: it is how non-semantic users will actually arrive; without it, stories 1 and
2 require a conversion step that defeats their purpose.

**Independent Test**: write the same five rows as CSV, Parquet, JSONL, a polars DataFrame, a pandas
DataFrame and a list of dicts; a keyword search and a whole-corpus request over each return the
same ids in the same order.

**Acceptance Scenarios**:

1. **Given** a CSV with columns `post_id` and `body`, **When** the user names them as id and text
   columns and asks for the whole table, **Then** every row is a candidate with `id` taken from
   `post_id` and `text` from `body`.
2. **Given** a Parquet file, a pandas DataFrame or a polars DataFrame with the same rows, **When**
   the same call is made, **Then** the result is identical.
3. **Given** a table with no id column named, **When** it is read, **Then** each row's id is its
   position in the table, and the documentation says these ids are only stable while the row order
   is.
4. **Given** a table with a missing column, an empty or missing text value, or a repeated id,
   **When** it is read, **Then** the call fails before any search, naming the column, or the first
   offending row and its value, and never drops or invents rows.
5. **Given** a table with an embedding column, one list of numbers per row, and the embedding model
   named, **When** a seed search runs with that model, **Then** it returns the same similarities,
   ranking and bands as before for the same vectors, and refuses an embedder whose model name
   differs from the one the table declares.
6. **Given** a table with no embedding column, **When** a seed search is asked for, **Then** it
   fails with a message that says the table has no embedding column and that keyword and
   whole-corpus calls need none.
7. **Given** a Parquet file when neither polars nor a Parquet-capable pandas is installed, **When**
   it is read, **Then** the call fails with a message that names what to install; importing the
   library never imports either.

---

### Edge Cases

- A term that is empty, or only whitespace, is refused: it would match every item and the user
  meant `everything`.
- An empty list of terms is refused. A bare string instead of a list of terms is refused with the
  same message style as seeds.
- A limit of zero or less is refused; `None` (the default) means no limit.
- An empty corpus returns an empty result, not an error.
- Items with the same text but different ids stay separate rows; ids are never merged.
- Text that contains regular-expression characters is matched literally when the term is a plain
  string and the regex option is off.
- A corpus with no embeddings at all is valid for whole-corpus and keyword calls: a table with no
  embedding column, or a Postgres table with no embedding column. These calls never read vectors,
  so a missing, malformed or mismatched embedding column does not fail them (a seed search still
  does, with a message naming what is missing).
- Embedding values can come from Parquet, JSONL, a DataFrame or a list of rows. A CSV cannot hold a
  list of numbers, so a CSV with an embedding column named is refused with a message that points to
  Parquet or JSONL.
- `LocalCorpus` no longer exists: using it raises the ordinary Python error for a missing name. The
  library is unpublished, so nothing is kept for it: no alias, shim, warning or migration note.
- Postgres rows have no inherent order, so "the corpus's own order" for a Postgres table is ascending
  by its id column. This is what makes server-side and Python-side results comparable and a limit
  repeatable.
- Whole-corpus and keyword lists use no embedder, so they record no embedding model and ask for
  none; a later classification is estimated and capped by `max_cost` exactly as before, and an
  unknown price still shows as `?`.
- Classifying a large whole-corpus list is the user's decision: the library shows the estimate
  first, as it already does, and never starts a run by itself.
- A table is read into memory whole; a file too large for memory is out of scope (filter it
  upstream or load it into Postgres). A table's own order is its row order.
- Ids are read as text, so a numeric id column gives the same ids as the same data in a text
  column. Extra columns are ignored by the library and not carried into the candidate rows.
- An embedding value that is not a list of numbers, or a vector whose length differs from the
  others, fails the seed search naming the first offending row; keyword and whole-corpus calls never
  look at the embedding column.
- One corpus per call. A user with several corpora calls once per corpus and combines the results
  before the library sees them. Candidate and gold files identify an item by its `id` alone, so
  ids that repeat across corpora would be treated as the same item; the library does not detect
  this, and the documentation says so.
- Connections are described in code by the corpus object (the database URL stays in the environment
  variable the corpus names); nothing is read from or written to a shared registry or a
  system-wide location.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to get a candidate list holding every item of a table, a S3 Vectors index
  or a Postgres corpus, without seeds, an embedder or a cutoff, and MUST NOT need embeddings to do
  so where the storage allows it (tables and Postgres; an S3 Vectors index always holds vectors).
- **FR-002**: Users MUST be able to get a candidate list of the items that match any of a list of
  terms. A term is a plain string (matched as literal text without regard to case, unless the
  regex option is on) or a compiled regular expression (always matched as a pattern, carrying its
  own flags).
- **FR-003**: Each term MUST be applied to every item independently of the others; one term's
  flags MUST NOT affect another's. An invalid pattern MUST fail before the corpus is read, naming
  the pattern.
- **FR-004**: Keyword results MUST be ranked, best first, and every row MUST carry the value it
  was ranked by. Ties MUST keep the corpus's order. [NEEDS CLARIFICATION: the ranking rule; see
  question 1.]
- **FR-005**: Both calls MUST accept a `limit` (default none, meaning no limit). A limit keeps the
  best-ranked items for keywords, and the first items in corpus order for the whole corpus. A limit
  below one MUST be refused.
- **FR-006**: Users MUST be able to ask a Postgres corpus to do the matching on the database
  server with an option on the keyword call. The statement MUST be read-only, MUST pass every user
  term as a bound parameter and every identifier through the existing identifier quoting, and MUST
  return the same ids in the same order as the Python-side match for plain-text terms. Asking for
  it on a non-Postgres corpus MUST fail with a clear message. [NEEDS CLARIFICATION: how regular
  expressions and their flags behave server-side; see question 2.]
- **FR-007**: Both calls MUST have an async and a sync form, the sync form working inside a running
  notebook event loop, and both MUST write the result like a seed search does (`out`: default
  location, a path, or nothing).
- **FR-008**: Every candidate MUST keep its corpus `id` and `text`; each item MUST appear at most
  once; whole-corpus order MUST be the corpus's own order (row order for a table, ascending id for a Postgres
  table).
- **FR-009**: A candidate list MUST record how it was built: from seeds, from keywords or from the
  whole corpus, and this MUST survive writing and reading the file.
- **FR-010**: A list not built from seeds MUST NOT carry a similarity or a best seed, and MUST NOT
  invent one. Its text and HTML display MUST state the count and the source in words, MUST show the
  rank where there is one, and MUST show no similarity bands, floor, similarity column or seed
  column.
- **FR-011**: Operations that only mean something with a similarity (items above a cutoff, top
  seeds, band counts, the per-band sample) MUST fail clearly on such a list, naming its source,
  and MUST work unchanged on a seed-search list. Seed search MUST keep ranking by similarity, best
  first.
- **FR-012**: Sampling, drawing gold rows, classifier estimate and classification, and the table
  exports (`to_polars` and `to_pandas`, together) MUST work on every list regardless of source.
- **FR-013**: Candidate files written before this feature (no recorded source) MUST load as
  seed-search results with identical behaviour.
- **FR-014**: Reading a corpus for these calls MUST be read-only (no write to the database,
  bucket or corpus files). Without the server-side option, keyword searches over Postgres and S3
  MUST hold no more than one batch of unmatched items at a time, plus the kept matches (at most
  `limit` of them when a limit is given). A whole-corpus Postgres request that exceeds the corpus's
  own result-size limit MUST be refused.
- **FR-015**: The feature MUST NOT write, infer or suggest a gold label, and MUST NOT add any way
  to set one.
- **FR-016**: The feature MUST NOT add a registry of sources, a shared or system-wide store, or a
  second way to describe a connection; corpora are described in code as they are today.
- **FR-017**: The public names, the agent skill and its references, the agent-instructions block
  and the README MUST describe the new calls and when to prefer seeds, keywords or the whole
  corpus; the existing drift tests MUST keep passing.
- **FR-018**: Importing the library MUST still do no I/O and import no optional dependency.
- **FR-019**: A seed search against a corpus that has no embeddings MUST fail with a message that
  names what is missing (the vector file, its metadata, or the embedding column). The text of the
  documentation and the agent instructions MUST stop describing hunches as working only over an
  already-embedded corpus.
- **FR-020**: Users MUST be able to describe a table as a corpus from a CSV file, a Parquet file, a
  JSONL file, a pandas DataFrame, a polars DataFrame or a list of row dicts, naming the text column
  and optionally the id column (default id: row position) and an embedding column with the
  embedding model's name. The same descriptor MUST work with the keyword, whole-corpus and (when
  an embedding column and model are given) seed-search calls.
- **FR-021**: Reading a table MUST fail, before any search, on a missing named column, a missing or
  empty text value, or a repeated id, naming the column or the first offending row. It MUST NOT
  drop, repair or invent rows.
- **FR-022**: DataFrames MUST be accepted without the library importing pandas or polars itself
  (importing the library stays free of both); a Parquet file MUST be readable with polars or a
  pandas that has a Parquet engine, and MUST fail with a message naming what to install when
  neither is available. No new dependency is added to the project.
- **FR-023**: A seed search over a table MUST compare the embedding model the table declares with
  the embedder's, refusing on a difference and refusing when none was declared.
- **FR-024**: `LocalCorpus` MUST be removed from the public names, the code, the documentation
  (README, `AGENTS.md`), the agent skill and references, the example and the tests, replaced by
  `Table`; no alias or deprecation shim is kept. Seed search, its bands, candidate files and
  everything downstream keep their behaviour. The documentation MUST describe only the format a
  table should have (the text column, the optional id column, the embedding column and model for
  seed search, which file types and DataFrames are accepted) and MUST NOT mention the removed
  corpus or its folder layout.

### Key Entities *(include if feature involves data)*

- **Candidate list**: the items proposed for classification, each with `id` and `text`. A list built
  from seeds also carries, per item, its best similarity and the seed that won it, plus the cutoff
  and embedding model. A list built from keywords carries, per item, its rank value. A list built
  from the whole corpus carries neither. Every list records its source.
- **Corpus**: a table, an S3 Vectors index or a Postgres table. This feature gives each of them
  one thing they lack: a way to read their items one batch at a time, without vectors, and, for
  Postgres, a way to have the server do the matching. A table or Postgres corpus is valid without
  embeddings; the Postgres descriptor keeps its name, and its embedding column is only used by seed
  search. The previous local-folder corpus is gone.
- **Table**: a corpus described from a CSV, Parquet or JSONL file, a pandas or polars DataFrame or a
  list of row dicts: the source, the text column, optionally the id column, optionally an embedding
  column and the embedding model's name. Held in memory.
- **Term**: a plain string or a compiled regular expression with its own flags.

## Deliberately skipped *(Ponytail)*

- Stemming, lemmatising, accent folding and fuzzy matching: literal case-insensitive text or a
  regular expression covers it; users who need more write the regex.
- "All terms" or boolean (AND/NOT) matching: any-term only; a user filters further with polars.
- A relevance model beyond the one rule chosen in question 1 (no BM25, no tf-idf, no
  database full-text ranking) and any user-supplied scoring function.
- Merging several corpora, or a list per corpus inside one call: one corpus per call, merging is
  upstream of the library.
- A registry of sources, saved connections or any system-wide storage.
- Server-side filtering for S3 Vectors or a table; S3 Vectors metadata filters.
- A non-vector S3 corpus (plain objects or a different store): an S3 Vectors index is the only S3
  kind.
- A converter, a shim, a deprecation period or a migration note for `LocalCorpus` (the library is
  unpublished), and a replacement for its compact `vectors.npy` storage (embedding columns in
  Parquet are the supported way).
- Renaming `PgCorpus` or adding a second Postgres descriptor for tables without embeddings; and
  reworking `PgCorpus.check`, which keeps reporting on the vector setup (its use on a table with no
  embedding column is noted in the docs, not redesigned).
- Server-side ranking or limiting: the database only filters; ranking and limit are applied in the
  library so that both backends rank alike.
- Embedding a table's text for seed search (a new cost, cache and model dependency): a table needs
  its embeddings supplied; computing them is a separate feature if wanted.
- Other table sources (Excel, SQL queries, Arrow IPC, globs of many files, URLs and cloud paths),
  streaming a table larger than memory, several text columns, carrying extra columns into the
  candidates, and writing tables out.
- Reading or writing vectors, or re-embedding, in the keyword and whole-corpus calls.
- A command-line entry point, a new file format, or a base class of "sources".

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from a corpus to a classification estimate in three calls with no
  seeds, no embedder and no embedding cost (estimate shows classifier cost only).
- **SC-002**: For hand-written fixtures of at least five items, a keyword search and a whole-corpus
  request return exactly the expected ids, in the expected order, with no duplicates, including a
  fixture with three expressions carrying three different flags.
- **SC-003**: 100% of the existing candidate, gold, evaluation and pre-006 compatibility tests pass
  without edits to their expectations.
- **SC-004**: No keyword or whole-corpus display contains a similarity value, a band row or the
  word "floor"; every one states its count and source.
- **SC-005**: Every similarity-only operation on a non-seed list fails with one message that names
  the list's source; none returns a wrong or empty answer silently.
- **SC-006**: A keyword search over a stubbed remote corpus of at least ten times the batch size
  returns only the matching rows and issues no write; with a limit it never holds more than that
  many ranked matches.
- **SC-008**: A table with no embedding column, and a stubbed Postgres table
  with only id and text columns, each produce a keyword list and a whole-corpus list with no error
  and no read of a vector.
- **SC-009**: The same five rows given as CSV, Parquet, JSONL, a polars DataFrame, a pandas
  DataFrame and a list of dicts produce identical keyword and whole-corpus results.
- **SC-007**: On a fixture of plain-text terms, the server-side and Python-side searches return
  identical ids in identical order; no user term appears inside the statement text.

## Assumptions

- **Matching rule**: terms are checked against the item's text only; any term suffices. Plain
  strings are matched case-insensitively with ordinary Unicode case folding, not locale-aware.
- **Regular expressions**: compiled patterns are the way to give a term its own flags; the regex
  option applies to plain strings and gives them no flags (inline flags written in the pattern
  still work). Flag behaviour is Python's for the Python-side search.
- **Scope**: the whole-corpus list is held in memory like every other candidate list. For Postgres
  the existing result-size limit is the guard; a truly larger-than-memory whole-corpus
  classification is out of scope (keyword-filter, limit or sample first).
- **S3 Vectors**: the corpus's text is read from item metadata the same way a search reads it, and
  a missing text field is an error, as it is today. Whether the service can list a whole index
  with that metadata is checked against its current docs in the plan, not assumed here.
- **Naming and exports**: the new calls are `hn.keywords(corpus, terms, regex=False, limit=None,
  ...)` and `hn.everything(corpus, limit=None, ...)` with async forms `akeywords` and
  `aeverything`, following the existing `search`/`asearch` pair; the server-side option's name and
  the plan's other names are confirmed in the plan.
- **Compatibility**: a seed-search result keeps its exact fields and display; only candidates built
  by the new calls omit the similarity fields.
- **No new dependency**: matching and CSV/JSONL reading use the standard library; DataFrames are
  used through their own methods, not imported by the library; Parquet needs polars or pandas with
  pyarrow, which the user installs (polars reads Parquet natively; pandas' `read_parquet`
  requires pyarrow, per their documentation). The plan checks the installed versions.
- **Local semantic corpora**: seed search over a table reads its embedding column into memory and
  compares with the same cosine-similarity maths as before; it is not a compact binary format, so
  very large embedded corpora belong in Postgres or S3 Vectors. The declared model name is the
  user's statement: the check guards against searching with a different embedder than the one the
  user declared, not against a wrong declaration.
- **Table naming**: the descriptor is provisionally `hn.Table(source, text_column="text",
  id_column=None, vector_column=None, embedding_model=None)`, mirroring `PgCorpus`'s column
  arguments; the plan confirms it. It is one more corpus kind, not a base class.
- **Semantic mode from tables**: supported when the table carries the embeddings. Embedding the
  text inside hunches is not part of this feature.
- **Verification**: everything runs against hand-built tables, the fake `psycopg` and a
  stubbed S3 client; a real database or bucket is a human step, recorded as such.

## Open questions *(for the user; resolve with `/speckit-clarify`)*

1. **Ranking rule for keyword hits.** Semantic hits are ranked by a similarity score. A keyword has
   no such score, so one must be chosen. Options: **A (recommended)** the number of distinct terms
   that matched, then the total number of matches, then corpus order, shown as two columns; **B** a
   single weighted score such as total matches only; **C** a relevance model such as BM25 (new
   behaviour, needs corpus-wide statistics, so a second pass over the corpus).
2. **Regular expressions on the database server.** Python and PostgreSQL differ: a compiled
   pattern's flags are Python's, while the database takes its own option letters, and its default
   treatment of line breaks is the opposite of Python's. Options: **A (recommended)** server-side
   supports plain text and the case-insensitive flag only, and refuses any other flag or a pattern
   it cannot translate, naming it; **B** server-side regular expressions are written in the
   database's own language and are documented as such, so results may differ from the Python side;
   **C** no regular expressions server-side, plain text only.

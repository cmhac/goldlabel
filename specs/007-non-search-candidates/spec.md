# Feature Specification: Non-search candidate sources

**Feature Branch**: `ccr-26b50054-jcevqw` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-10-26

**Status**: Draft

**Input**: User description: "Non-search candidate sources for the hunches library: let a user build a Candidates list without semantic seed search. (1) a keyword/regex candidate list over a corpus, and (2) the whole corpus with no filtering. Today `Candidates` rows assume `max_similarity` and `best_seed`, so its repr, bands, above, top_seeds and band_sample break on rows without them; the corpus classes (LocalCorpus, S3Corpus, PgCorpus) have no plain item reader, only the search code reads items. Proposed shape (to be refined in the spec): make similarity fields optional on Candidates with plain-count fallbacks in repr/_repr_html_, record a `source` ("seeds", "keywords", "all"), and add `hn.keywords(corpus, terms, regex=False)` and `hn.everything(corpus)` with a streaming item reader for all three corpus types (pgvector tables can be larger than memory). Must keep: no I/O on import, async+sync forms, polars+pandas export, unknown cost shown as `?`, never touch gold labels, minimal implementation with no abstractions."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Classify the whole corpus, no filtering (Priority: P1)

A user whose corpus is small enough, or whose question is "label everything", wants every item in
the corpus as a candidate list without writing seed phrases or choosing a similarity cutoff. The
result behaves like any other candidate list: it shows how many items it holds, can be sampled for
the labelling page, and can be handed to the classifier.

**Why this priority**: it is the simplest case and the one with the least new behaviour: no
matching logic, only a way to read a corpus's items and a candidate list that does not pretend its
items have a similarity. Everything in story 2 needs the same two pieces.

**Independent Test**: build a candidate list from a tiny local corpus with no seeds and no
embedder, check it holds every item exactly once, draw gold rows from it, and estimate a
classification of it, all without any model call.

**Acceptance Scenarios**:

1. **Given** a corpus of five items, **When** the user asks for the whole corpus, **Then** the
   result holds five candidates, each with its `id` and `text`, in the corpus's own order.
2. **Given** that result, **When** it is shown, **Then** the text says it holds five candidates
   and that it came from the whole corpus; it shows no similarity bands, no similarity column and
   no seed column.
3. **Given** that result, **When** the user draws gold rows from it and estimates a classification
   of it, **Then** both work exactly as they do for a seed-search result.
4. **Given** that result, **When** the user asks for the items above a similarity cutoff, for
   the top seeds, or for a per-band sample, **Then** the call fails at once with a message that
   says this list has no similarity because it was not built from seeds.

---

### User Story 2 - A keyword or regex candidate list (Priority: P2)

A user who already knows words that mark the items they care about (a name, a phrase, a hashtag)
wants the items that contain them, without embedding anything and without paying for an embedding
call.

**Why this priority**: it is the most common "simple filter" and it is the reason the question was
asked, but it needs story 1's reader and list first.

**Independent Test**: on a tiny local corpus, ask for items containing a plain term, then for items
matching a regular expression, and check the exact ids returned against a hand-written expectation.

**Acceptance Scenarios**:

1. **Given** a corpus where items 2 and 4 contain "ballot", **When** the user asks for the keyword
   "ballot", **Then** the result holds exactly items 2 and 4, whatever their case ("Ballot",
   "BALLOT").
2. **Given** two terms, **When** the user asks for items matching them, **Then** an item that
   contains either term is included once.
3. **Given** the term `r"vote[sd]?\b"` and the regex option on, **When** the search runs, **Then**
   items matching the pattern are returned; with the option off the same string is matched as
   literal text.
4. **Given** a term that matches nothing, **When** the search runs, **Then** the result is empty
   and says so in words (0 candidates), not an error.
5. **Given** an invalid regular expression, **When** the user asks for it, **Then** the call fails
   before reading the corpus, with a message that names the pattern.
6. **Given** the result, **When** it is shown, **Then** it says it came from keywords, gives the
   count, and shows no similarity bands.

---

### User Story 3 - Existing searches and saved files are unchanged (Priority: P1)

A user with a seed-search result, a `candidates.jsonl` written by an earlier version, or a
notebook using the band report must see exactly what they saw before.

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
   keeps its source and shows no bands.

---

### User Story 4 - Large pgvector and S3 corpora do not need to fit in memory to be keyword-searched (Priority: P3)

A user with a corpus in a pgvector table or an S3 Vectors index, larger than memory, wants a
keyword list from it. Only the matching items are kept.

**Why this priority**: a matching local corpus covers the main need; the read-only remote readers
are the same feature on bigger data and cannot be verified without a real database or bucket.

**Independent Test**: with the fake database and a stubbed S3 client, a keyword search over more
rows than are held at once returns only the matches, and the number of rows held at any moment is
bounded by a batch, not by the corpus.

**Acceptance Scenarios**:

1. **Given** a pgvector or S3 corpus, **When** a keyword search runs, **Then** every item is read
   once, only matches are kept, and nothing is written to the database or the bucket.
2. **Given** a pgvector corpus and a request for the whole corpus, **When** the table is larger than
   the corpus's own result-size limit, **Then** the call refuses with a message that names the
   limit instead of exhausting memory.

---

### Edge Cases

- A term that is empty, or only whitespace, is refused: it would match every item and the user
  meant `everything`.
- An empty list of terms is refused.
- A bare string instead of a list of terms is refused with the same message style as seeds.
- An empty corpus returns an empty result, not an error.
- Items with the same text but different ids stay separate rows; ids are never merged.
- Text that contains regular-expression characters is matched literally when the regex option is
  off.
- A corpus whose item file and vector file disagree in length: whole-corpus and keyword reads do not
  use vectors, so they do not fail on it (a seed search still does).
- Whole-corpus and keyword lists use no embedder, so they record no embedding model and ask for
  none; a later classification is estimated and capped by `max_cost` exactly as before, and an
  unknown price still shows as `?`.
- Classifying a large whole-corpus list is the user's decision: the library shows the estimate
  first, as it already does, and never starts a run by itself.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to get a candidate list holding every item of a local, S3 or
  pgvector corpus, without seeds, an embedder or a cutoff.
- **FR-002**: Users MUST be able to get a candidate list of the items whose text contains any of a
  list of terms, matched without regard to case, as literal text by default.
- **FR-003**: Users MUST be able to switch the terms to regular expressions with one option; an
  invalid pattern MUST fail before the corpus is read, naming the pattern.
- **FR-004**: Both calls MUST have an async and a sync form, the sync form working inside a running
  notebook event loop, and both MUST write the result like a seed search does (`out`: default
  location, a path, or nothing).
- **FR-005**: Every candidate MUST keep its corpus `id` and `text`. Order MUST be the corpus's own
  order, and each item MUST appear at most once.
- **FR-006**: A candidate list MUST record how it was built: from seeds, from keywords or from the
  whole corpus, and this MUST survive writing and reading the file.
- **FR-007**: A list not built from seeds MUST NOT carry a similarity or a best seed, and MUST NOT
  invent one. Its text and HTML display MUST state the count and the source in words and MUST show
  no similarity bands, floor, similarity column or seed column.
- **FR-008**: Operations that only mean something with a similarity (items above a cutoff, top
  seeds, band counts, the per-band sample) MUST fail clearly on such a list, naming its source,
  and MUST work unchanged on a seed-search list.
- **FR-009**: Sampling, drawing gold rows, classifier estimate and classification, and the table
  exports (`to_polars` and `to_pandas`, together) MUST work on every list regardless of source.
- **FR-010**: Candidate files written before this feature (no recorded source) MUST load as
  seed-search results with identical behaviour.
- **FR-011**: Reading a corpus for these calls MUST be read-only (no write to the database,
  bucket or corpus files), MUST NOT hold more than one batch of unmatched items at a time for
  keyword searches over pgvector and S3 corpora, and MUST refuse a whole-corpus pgvector request
  that exceeds the corpus's own result-size limit.
- **FR-012**: The feature MUST NOT write, infer or suggest a gold label, and MUST NOT add any way
  to set one.
- **FR-013**: The public names, the agent skill and its references, the agent-instructions block
  and the README MUST describe the new calls and when to prefer seeds, keywords or the whole
  corpus; the existing drift tests MUST keep passing.
- **FR-014**: Importing the library MUST still do no I/O and import no optional dependency.

### Key Entities *(include if feature involves data)*

- **Candidate list**: the items proposed for classification, each with `id` and `text`. A list built
  from seeds also carries, per item, its best similarity and the seed that won it, plus the cutoff
  and embedding model. A list built from keywords or the whole corpus carries neither. Every list
  records its source.
- **Corpus**: the existing local, S3 and pgvector descriptors. This feature adds one thing they
  lack: a way to read their items one batch at a time, without vectors.
- **Terms**: the user's keywords or regular expressions, in a list, never a bare string.

## Deliberately skipped *(Ponytail)*

- Stemming, lemmatising, accent folding and fuzzy matching: literal case-insensitive text or a
  regular expression covers it; users who need more write the regex.
- "All terms" or boolean (AND/NOT) matching: any-term only; `Candidates` rows can be filtered with
  polars afterwards.
- Recording which term matched each item: no stage uses it.
- Server-side filtering in pgvector (`ILIKE`, `~`) and S3 metadata filters: the same client-side
  match everywhere keeps one behaviour; upgrade only if reading a huge table is too slow.
- A cap, sampling or `limit` argument on the whole-corpus call: `sample` and the existing
  result-size limit already do that.
- Mixing sources (keywords plus seeds, or union of lists): one source per list.
- Reading or writing vectors, or re-embedding, in the new calls.
- A command-line entry point, a new file format, or a base class or registry of "sources".
- Any similarity score or ranking for keyword hits (term counts, BM25): order is the corpus's.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from a corpus to a classification estimate in three calls with no
  seeds, no embedder and no embedding cost (estimate shows classifier cost only).
- **SC-002**: For hand-written fixtures of at least five items, a keyword search and a whole-corpus
  request return exactly the expected ids, in order, with no duplicates.
- **SC-003**: 100% of the existing candidate, gold, evaluation and pre-006 compatibility tests pass
  without edits to their expectations.
- **SC-004**: No keyword or whole-corpus display contains a similarity value, a band row or the
  word "floor"; every one states its count and source.
- **SC-005**: Every similarity-only operation on a non-seed list fails with one message that names
  the list's source; none returns a wrong or empty answer silently.
- **SC-006**: A keyword search over a stubbed remote corpus of at least ten times the batch size
  keeps a result containing only the matching rows, and issues no write.

## Assumptions

- **Matching rule**: terms are checked against the item's text only, case-insensitively, any term
  suffices. Case folding is plain Unicode case-insensitivity, not locale-aware.
- **Scope**: the whole-corpus list is held in memory like every other candidate list. For a
  pgvector corpus the existing result-size limit is the guard; for a local corpus the item file is
  the memory the user already has. A truly larger-than-memory whole-corpus classification is out
  of scope (the user should keyword-filter or sample first).
- **S3 Vectors**: the corpus's text is read from item metadata the same way a search reads it, and
  a missing text field is an error, as it is today. Whether the service can list a whole index
  with that metadata is checked against its current docs in the plan, not assumed here.
- **Naming and exports**: the new calls are `hn.keywords(corpus, terms, regex=False, ...)` and
  `hn.everything(corpus, ...)` with async forms `akeywords` and `aeverything`, following the
  existing `search`/`asearch` pair; the plan confirms the names.
- **Compatibility**: a seed-search result keeps its exact fields and display; only candidates built
  by the new calls omit the similarity fields.
- **No new dependency**: matching uses what the library already ships with.
- **Verification**: everything runs against hand-built local corpora, the fake `psycopg` and a
  stubbed S3 client; a real database or bucket is a human step, recorded as such.

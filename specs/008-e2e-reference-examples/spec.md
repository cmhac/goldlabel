# Feature Specification: End-to-end reference examples

**Feature Branch**: `ccr-26b50054-jcevqw` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-10-27

**Status**: Draft, Q1 resolved 2026-10-27 (ready for `/speckit-clarify`, then `/speckit-plan`)

**Input**: User description: "Runnable end-to-end reference examples in an e2e/ folder, one per primary path a user can take with the hunches library, each runnable fully locally against podman-run emulators (Postgres, Postgres with pgvector, Floci for S3 Vectors) plus a required real LLM API key for the classifier, never run in local pre-commit hooks or CI by default, kept up to date as source code and pointed to from the README as the reference for different implementations."

**Decisions already made (user, 2026-10-27)**: a real API key is acceptable for the examples that call a model; no visual checks; Floci is sufficient for S3 Vectors, no real AWS behaviour; the folder is called `e2e/`, not `examples/`, and the README tells users to use it as the reference for their kind of setup; these runs are not part of the pre-commit hooks or CI, and how often CI runs them is a later decision that depends on what they cost to run; the constitution's rule against tests that depend on real services was meant to keep tests off real external services, not off isolated local emulators, so these runs are allowed to use them. The gold rule is **not** relaxed (see "Gold labels" below).

## Clarifications

### Session 2026-10-27

- Q: Should each example be a plain script, an automated test, or both? → A: Plain scripts, one per example folder, that check their own results and exit non-zero on failure, plus one run-all script that prints a single summary. A thin test wrapper may be added later without changing the examples. The project's default test run only collects `tests/`, so `e2e/` is never run by it.
- Q: Should the examples share one data file? → A: No. Each example folder is self-contained: it defines its own small data and expected values, and does not import another example's files. The container start and stop code is repeated in each example that needs it. Agreement between the examples' data is held by a fast offline check in `tests/`.
- Q: Which local file inputs are covered? → A: One table example script that shows every way of loading local data (CSV, Parquet read through polars, Parquet read through pandas, JSONL, a polars DataFrame, a pandas DataFrame and a list of rows). Every form is loaded and must give the same whole corpus. Keywords and seeds are demonstrated on a few representative forms, not on every form: no exhaustive form-by-mode grid is required, and the user said the examples do not need to be structured as many clean automated tests.
- Note: "a user can copy a folder" was an assumption in the first draft, not a requirement from the user. The goal is that a reader can use each folder as a reference for that setup.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Table paths run with nothing installed but Python (Priority: P1)

A user whose corpus is a file or a DataFrame wants a worked, runnable example of each way to get
candidates from it: the whole corpus, keywords and regular expressions (with flags, ranking and a
limit), and seed phrases. They read the folder, run one command, and see the candidates and a
pass or fail summary. No container, database or key is needed.

**Why this priority**: it is the path most users take first, it needs no setup, and it carries the
checks the other paths are compared against.

**Independent Test**: run the table example on a machine with no container tool and no key; it
finishes, prints the candidates for each of the three ways, and every result matches the expected
values written in the example.

**Acceptance Scenarios**:

1. **Given** a small corpus supplied as a CSV file, a Parquet file read through polars, a Parquet
   file read through pandas, a JSONL file, a polars DataFrame, a pandas DataFrame and a list of
   rows, **When** the example asks for the whole corpus from each, **Then** all seven give the
   same ids in the same order.
2. **Given** that corpus as a file and as a DataFrame, **When** the example searches by keywords
   and regular expressions, **Then** the ranked hits, their term and match counts, and a limited
   list all equal the values written in the example by hand, and are the same for both.
3. **Given** the corpus with embeddings as a JSONL file, a Parquet file and a DataFrame, **When**
   the example searches by seed phrases with a stand-in embedder, **Then** the similarities, bands
   and best seeds equal the hand-computed values for all three, and no key is needed. **And** a
   CSV given a vector column is refused with a message that names the reason.
4. **Given** any expected value that is wrong, **When** the example runs, **Then** it stops with a
   message that names the check that failed and both values.

---

### User Story 2 - Postgres paths run against throwaway databases (Priority: P1)

A user whose corpus lives in Postgres wants an example for each Postgres path: reading without
embeddings (whole corpus, keywords, and server-side filtering), the same with the text in a
second table, and seed search on a pgvector table in both exact and index modes. The example
starts a throwaway database, loads the data, runs, checks, and removes the database.

**Why this priority**: Postgres is the main large-corpus backend and its behaviour (server-side
matching, ordering, size limits, two-table layout) is exactly what a copied example must get
right.

**Independent Test**: with a container tool installed and no key, run the Postgres examples; each
creates its database, finishes with a pass summary, and leaves no container behind.

**Acceptance Scenarios**:

1. **Given** the example corpus loaded into a plain Postgres table, **When** the example
   asks for the whole corpus and for keywords, **Then** the results equal the table example's.
2. **Given** the same text split across two tables, **When** the example repeats those calls,
   **Then** the results are identical to the one-table results.
3. **Given** terms that contain the wildcard characters `%` and `_` and a backslash, and a regular
   expression with an inline flag, **When** the example runs each with server-side filtering on
   and off, **Then** both give the same hits and the same ranking.
4. **Given** the same corpus with embeddings in a pgvector table, **When** the example searches by
   seeds in exact mode and in index mode, **Then** exact mode equals the table example's
   similarities and index mode returns the same items for the example's data.
5. **Given** a table that is too big for the result size limit, **When** the example asks for the
   whole corpus, **Then** the call is refused with the limit in the message, and a `limit` or a
   keyword filter gets past it.

---

### User Story 3 - S3 Vectors paths run against an emulator (Priority: P2)

A user whose corpus lives in an S3 Vectors index wants an example of the whole corpus, keywords
and seed search against it, without an AWS account. The example starts an S3 emulator, creates a
vector bucket and index, loads the example corpus, runs, checks, and removes the emulator.

**Why this priority**: it is the only way to exercise the S3 reader and the S3 seed search
without AWS, and only one of the three backends.

**Independent Test**: with a container tool installed and no key, run the S3 example; it passes
and cleans up.

**Acceptance Scenarios**:

1. **Given** the example corpus loaded into an index, **When** the example asks for the whole
   corpus, **Then** it gets every item once, including when the index holds more items than one
   page of the listing.
2. **Given** that index, **When** the example searches by keywords and by seeds, **Then** the
   candidates equal the table example's (the order of a whole-corpus listing is the service's own,
   and the example says so instead of asserting it for real AWS).

---

### User Story 4 - Classify, estimate and evaluate end to end (Priority: P2)

A user wants a worked example of the rest of the chain once they have candidates: draw gold rows,
bring labels people made, estimate the cost, classify with a real model, evaluate against the gold
rows, and read the disagreements. It runs against a small corpus with a spend cap, and it needs a
real model key.

**Why this priority**: it is the part that costs money and needs human-made data, so it is the
last to build, but it is what makes the examples a complete reference.

**Independent Test**: with a model key in the environment, run the example; it prints the cost
estimate before any model call, stays under its spend cap, and prints an evaluation. Without a
key it stops before any model call and says what is missing.

**Acceptance Scenarios**:

1. **Given** no key in the environment, **When** the example runs, **Then** it stops before any
   model call with a message naming the missing variable, and the examples that need no key are
   unaffected.
2. **Given** a key, **When** the example runs, **Then** the estimate is shown before the first
   model call, the run has a cost cap, and an unknown price makes it refuse rather than run.
3. **Given** the human-made labelled rows (see "Gold labels"), **When** the example imports them,
   **Then** they are imported unchanged and the evaluation reports its scores, the number of rows,
   and where the labels came from.
4. **Given** the same example run a second time, **When** nothing changed, **Then** it makes no
   new model calls (the result cache is hit).

---

### User Story 5 - The README points to the examples and they stay current (Priority: P3)

A user reading the README is told that `e2e/` is the reference for the different ways to set the
library up, and which folder matches their corpus. A maintainer changing the library finds the
examples treated as source code: formatted, linted, type-checked and covered by a quick offline
check that they are still complete, but not run by the pre-commit hooks or CI.

**Why this priority**: without this the examples rot, but it only matters once they exist.

**Independent Test**: break an example's imports or remove one from the README; the normal quick
checks fail. Start the default checks with no container tool, no network and no key; they pass.

**Acceptance Scenarios**:

1. **Given** the README, **When** a user looks for how to set up Postgres, S3 or a file, **Then** a
   named `e2e/` folder is linked for each.
2. **Given** a change to the library's public names, **When** the default checks run, **Then** an
   example that still uses a removed name fails them, without starting any container.
3. **Given** the default checks and the pre-commit hooks, **When** they run, **Then** no example
   is executed; running them is a separate, explicit command.

---

### Edge Cases

- The container tool is missing: the example stops at the start with a message that names it and
  how to install it; it never falls back to another container tool.
- A required port is already in use, or a container from an earlier killed run is still there:
  the example says which, and a rerun cleans up what an earlier run left.
- An image has to be downloaded and the network is down: the example fails with the image name,
  not with a database error.
- The database or emulator is slow to start: the example waits for readiness up to a stated time,
  then fails with the container's recent log lines.
- The run fails or is interrupted halfway: the containers are still removed.
- The model key is wrong or the model's price is unknown: the run stops with the library's own
  refusal, before spending anything where possible.
- Two examples run at once: they do not collide (separate ports, names and data directories) or
  the second one says why it cannot start.
- The pandas Parquet engine is not installed: the Parquet-through-pandas check says so by name and
  is reported as skipped, not passed, and does not hide a failure of the other forms.
- The example writes files: they go to a temporary folder, not the repository.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST have an `e2e/` folder with one example for each of these paths,
  and no path without one: file and DataFrame tables (every supported input form loaded and checked
  for the whole corpus; keywords and regular expressions and seeds shown on representative forms); Postgres without embeddings (whole corpus, keywords, server-side
  filtering) in one-table and two-table layouts; Postgres with pgvector (seeds, exact and index
  modes); S3 Vectors (whole corpus, keywords, seeds); classify, estimate and evaluate.
- **FR-002**: Each example MUST be a self-contained folder with a README (what it shows, what it
  needs, the one command that runs it, what a pass looks like), a single script, and its own small
  data and expected values. An example MUST NOT import or read another example's files. Each folder
  MUST be readable on its own as the reference for that setup.
- **FR-018**: Each example MUST be run by a plain command and exit with a non-zero status on any
  failed check. One run-all command MUST run every example, print one summary line per example
  and a final one, and exit non-zero if any failed. A test-tool wrapper is NOT required.
- **FR-003**: Each example MUST check its own results against expected values written in the
  example by hand, MUST stop with a message that names the failed check and both values, and MUST
  end with a one-line pass or fail summary.
- **FR-004**: The table, Postgres and S3 examples MUST each define the same small corpus (the same
  texts, ids and embeddings, where embeddings apply) and the same expected results for the same
  filters, so a reader can compare them. A fast offline check MUST fail if those definitions drift
  apart. Where the order of a result is the service's own, the example MUST say so instead of
  asserting an order.
- **FR-005**: Examples that need a database or an S3 service MUST start it themselves in a
  throwaway container, wait until it is ready, load the data, and remove the container when done,
  also when the run fails or is interrupted.
- **FR-006**: All local container work MUST use Podman, never Docker, and no example, script or
  document may require a Docker daemon (constitution v1.1.0).
- **FR-007**: Examples MUST NOT use real cloud services, real databases or a real AWS account.
  Isolated containers on the user's own machine are allowed. The only real external service an
  example may call is the model provider in the classification example, with a key from the
  environment.
- **FR-008**: The classification example MUST need a model key from the environment, MUST stop
  before any model call when it is missing, MUST show the estimate before the first call, MUST set
  a cost cap, and MUST NOT run when the price is unknown. The other examples MUST NOT need a key.
  Seed search in the examples MUST use a stand-in embedder with hand-built vectors, so its
  results can be written down in advance and need no key.
- **FR-009**: Examples MUST NOT run in the pre-commit hooks or in CI by default, and the default
  test run MUST NOT start a container, call a model or use the network. How often CI runs them is
  out of scope here; this feature MUST leave that choice open and record what a run costs (time,
  and model spend for the classification example) so the choice can be made later.
- **FR-010**: Examples MUST be source code of the project: covered by the project's formatting,
  linting and type checks, and by a fast offline check that every path in FR-001 has its folder,
  that each folder has the parts in FR-002, that the README links each, and that an example uses
  only names the library exports.
- **FR-011**: The README MUST tell users to use `e2e/` as the reference for different
  implementations, and name which folder to read for which corpus kind. The agent-facing texts
  that name the example folder (`AGENTS.md`, the skill) MUST be updated to say `e2e/`.
- **FR-012**: The existing `examples/sample` walkthrough MUST be moved into `e2e/` as part of the
  classification path, `examples/` retired, and every reference to the old path (README, project
  notes, tests, lint configuration) updated.
- **FR-013**: Examples MUST write their files (candidates, cache, gold, results) to a temporary
  folder by default and MUST leave the repository's working tree unchanged after a run.
- **FR-014**: Containers MUST NOT contain or need real credentials; throwaway passwords and
  tokens are generated or fixed and local. No secret MAY be committed; model keys come only from
  the environment.
- **FR-015**: Examples MUST NOT write, edit, infer or complete a gold label. Gold rows used by
  any example MUST be human-labelled rows imported unchanged through the library's import of
  already-labelled rows, with their provenance (who labelled them and where they came from)
  recorded next to the data and shown in the example's output. No example, script, test or
  helper in this repository MAY contain a gold label that an agent or a model wrote. The gold
  rule and constitution Principle I stay exactly as they are.
- **FR-016**: The constitution MUST be amended (a MINOR change, with the user's approval) so that
  Principle IV's rule against calling real services in tests is read as applying to the default
  checks, and says that opt-in end-to-end runs under `e2e/` may use isolated local containers and
  the model provider in the classification example. The amendment MUST change nothing in
  Principle I.
- **FR-017**: Each example MUST state what it needs (container tool, key, optional libraries) and
  what it costs (time, and model spend), and MUST tell the user plainly what is missing when a
  need is not met.

### Key Entities

- **Example**: a folder under `e2e/` for one path. Has a README, runnable code, its data, expected
  values, and the list of what it needs.
- **Example corpus**: the small set of items (ids, texts, embeddings) that the table, Postgres and
  S3 examples each define for themselves, kept identical by an offline check, so their results
  can be compared.
- **Throwaway service**: a container started by an example for the length of one run: a plain
  Postgres, a Postgres with pgvector, or an S3 Vectors emulator.
- **Expected values**: results written by hand in an example and compared with what the library
  returns.
- **Human-labelled rows**: gold rows made by people, with their provenance, imported unchanged.

## Gold labels

Examples that evaluate need gold rows, and the gold rule says only people create them. These
examples therefore ship rows that people labelled (in the labelling page, or taken from a dataset
that people already labelled), with the provenance recorded. They are imported unchanged. Nothing
in this feature writes, completes or "bootstraps" a label, including for demonstration, and an
agent working on this feature who is asked to write demonstration labels MUST refuse and say so.
This was raised and decided on 2026-10-27: the request to let an agent write demonstration gold
labels was declined because the rule can only be changed by amending Principle I, which was not
done.

## Resolved question

- **Q1: where do the human-labelled rows come from?** Decided by the user on 2026-10-27, option A:
  the maintainer labels a few dozen rows in the labelling page and commits the resulting gold file
  and its provenance note with the classification example. No dataset is imported from elsewhere
  and the example does not pause for labelling. The file is committed exactly as the labelling page
  wrote it; nothing edits it afterwards. Until the file is committed, the classification example's
  evaluation step cannot run and says so; the other examples do not depend on it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer with the container tool installed can run any one example with a
  single documented command and get a pass or fail summary in under 5 minutes once the images are
  downloaded (10 minutes for the classification example).
- **SC-002**: For the same filter, the table, Postgres (one table and two tables), pgvector and S3
  examples return the same candidates (same ids; the same order except where the service's order
  applies), shown by the examples' own checks.
- **SC-003**: The default test run, the pre-commit hooks and CI run no container, no model call
  and no network access for these examples, and still fail when an example uses a removed library
  name or is missing from the README.
- **SC-004**: After any example run, passed, failed or interrupted, zero containers from it remain
  and the repository's working tree has no new or changed files.
- **SC-005**: Each of the paths in FR-001 has exactly one example, and the README links each one.
- **SC-006**: Zero gold labels in the repository were written by an agent or a model; every gold
  row an example uses is byte-identical to the human-labelled source it came from.
- **SC-007**: The classification example prints its cost estimate before its first model call,
  never exceeds its stated cost cap, and its total model spend for a full run is stated in its
  README (the target is well under one US dollar).
- **SC-008**: A second run of the classification example with nothing changed makes no model
  calls.

## Assumptions

- The examples are run by a maintainer or a user who has `podman` and `uv` installed; installing
  them is outside this feature, and the examples say so when they are missing.
- Container images come from public registries on first use (a plain Postgres, a pgvector
  Postgres and an S3 Vectors emulator); pulling them is allowed for these runs and the image
  names and versions are recorded with the example. The S3 emulator is Floci; its behaviour is a
  stand-in, and these examples make no claim about real AWS (ordering, permissions, throttling).
- Seed search in the examples uses a stand-in embedder with hand-built vectors, because the
  library only embeds seed phrases and a real embedding model would add a key, cost and
  non-determinism without testing any of the library's own logic.
- The classification example uses one small model from the provider the project already supports
  for classification, chosen for low cost; which one is a planning decision.
- Visual checks (the labelling page's look, notebook rendering) and IAM-based database login are
  out of scope.
- `examples/sample` is moved rather than kept, because two reference folders would confuse the
  README's instruction. Its notebook and script pair, and the tests that keep them in step, move
  with it.
- The existing end-to-end test in the test suite (which uses a stubbed model and a simulated
  person) stays where it is; it is part of the default checks and is a different thing from these
  opt-in runs, so the name `e2e/` for the folder is a naming overlap to be explained in the README.
- Containers use the host network or published ports on the user's machine only; no example opens
  anything to other machines.

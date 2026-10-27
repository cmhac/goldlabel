# Feature Specification: End-to-end reference examples

**Feature Branch**: `ccr-26b50054-jcevqw` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-10-27

**Status**: Draft, clarification in progress (all questions resolved 2026-10-27; ready for `/speckit-plan`)

**Input**: User description: "Runnable end-to-end reference examples in an e2e/ folder, one per primary path a user can take with the hunches library, each runnable fully locally against podman-run emulators (Postgres, Postgres with pgvector, Floci for S3 Vectors) plus a required real LLM API key for the classifier, never run in local pre-commit hooks or CI by default, kept up to date as source code and pointed to from the README as the reference for different implementations."

**Decisions already made (user, 2026-10-27)**: a real API key is acceptable for the examples that call a model; no visual checks; Floci is sufficient for S3 Vectors, no real AWS behaviour; the folder is called `e2e/`, not `examples/`, and the README tells users to use it as the reference for their kind of setup; these runs are not part of the pre-commit hooks or CI, and how often CI runs them is a later decision that depends on what they cost to run; the constitution's rule against tests that depend on real services was meant to keep tests off real external services, not off isolated local emulators, so these runs are allowed to use them. The gold rule is **not** relaxed (see "Gold labels" below).

## Clarifications

### Session 2026-10-27

- Q: Should each example be a plain script, an automated test, or both? → A: Plain scripts, one per example folder, that check their own results and exit non-zero on failure, plus one run-all script that prints a single summary. A thin test wrapper may be added later without changing the examples. The project's default test run only collects `tests/`, so `e2e/` is never run by it.
- Q: Which local file inputs are covered? → A: One table example script that shows every way of loading local data (CSV, Parquet read through polars, Parquet read through pandas, JSONL, a polars DataFrame, a pandas DataFrame and a list of rows). Every form is loaded and must give the same whole corpus. Keywords and seeds are demonstrated on a few representative forms, not on every form. The user said the examples do not need to be structured as many clean automated tests.
- Q: One corpus for every example, or a separate one for classification? → A: One corpus of about 60 items for every example, read from a common data folder. Every backend example runs the full chain (candidates, classify, evaluate) on its own backend, and a shared result cache means each item is classified by the model once, however many examples run. The user's reason: the same data lets the end-to-end results be compared across configurations without paying for the model again.
- Q: Should the detailed walkthrough stay a notebook-and-script pair? → A: It becomes a notebook only, with no script twin, and the run-all script runs it headlessly and treats a failing cell as a failed check. The notebook-equals-script drift test is dropped with the script. The notebook executor is a development-group dependency, which the constitution (amended to v1.2.0 on 2026-10-27) now allows for notebook libraries.
- Q: Does an example have to be a copyable, self-contained folder? → A: No. That was an assumption in the first draft, not the user's requirement. Each folder has its own README and script and is the reference for its setup; the common data lives in one place, and no example imports another example.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Table paths run with no container (Priority: P1)

A user whose corpus is a file or a DataFrame wants a worked, runnable example of each way to load
it and get candidates: the whole corpus, keywords and regular expressions (with flags, ranking and
a limit), and seed phrases. They read the folder, run one command, and see the candidates, then the
classification and evaluation that follow, and a pass or fail summary. No container or database is
needed.

**Why this priority**: it is the path most users take first, it needs no setup beyond Python, and
its results are what every other backend is compared against.

**Independent Test**: run the table example on a machine with no container tool and a model key; it
finishes, and every result matches the expected values written for it. Run it again with no key and
a filled result cache: it still finishes, with no model call.

**Acceptance Scenarios**:

1. **Given** the common corpus supplied as a CSV file, a Parquet file read through polars, a
   Parquet file read through pandas, a JSONL file, a polars DataFrame, a pandas DataFrame and a
   list of rows, **When** the example asks for the whole corpus from each, **Then** all seven give
   the same ids in the same order.
2. **Given** that corpus as a file and as a DataFrame, **When** the example searches by keywords
   and regular expressions, **Then** the ranked hits, their term and match counts, and a limited
   list all equal the values written in the example by hand, and are the same for both.
3. **Given** the corpus with embeddings as a JSONL file, a Parquet file and a DataFrame, **When**
   the example searches by seed phrases with a stand-in embedder, **Then** the similarities, bands
   and best seeds equal the hand-computed values for all three, and no key is needed for this step.
   **And** a CSV given a vector column is refused with a message that names the reason.
4. **Given** the candidates from the whole corpus, **When** the example classifies them and
   evaluates the dev split against the human-labelled rows, **Then** the evaluation scores equal
   those of every other example.
5. **Given** any expected value that is wrong, **When** the example runs, **Then** it stops with a
   message that names the check that failed and both values.

---

### User Story 2 - Postgres paths run against throwaway databases (Priority: P1)

A user whose corpus lives in Postgres wants an example for each Postgres path: reading without
embeddings (whole corpus, keywords, and server-side filtering), the same with the text in a
second table, and seed search on a pgvector table in both exact and index modes. The example
starts a throwaway database, loads the common corpus, runs the full chain, checks, and removes the
database.

**Why this priority**: Postgres is the main large-corpus backend and its behaviour (server-side
matching, ordering, size limits, two-table layout) is exactly what a reader needs a worked
reference for.

**Independent Test**: with a container tool installed, run the Postgres examples; each creates its
database, finishes with a pass summary, and leaves no container behind.

**Acceptance Scenarios**:

1. **Given** the common corpus loaded into a plain Postgres table, **When** the example asks for
   the whole corpus and for keywords, **Then** the results equal the table example's.
2. **Given** the same text split across two tables, **When** the example repeats those calls,
   **Then** the results are identical to the one-table results.
3. **Given** terms that contain the wildcard characters `%` and `_` and a backslash, and a regular
   expression with an inline flag, **When** the example runs each with server-side filtering on
   and off, **Then** both give the same hits and the same ranking.
4. **Given** the same corpus with embeddings in a pgvector table, **When** the example searches by
   seeds in exact mode and in index mode, **Then** exact mode equals the table example's
   similarities and index mode returns the same items for the common data.
5. **Given** a table that is too big for the result size limit, **When** the example asks for the
   whole corpus, **Then** the call is refused with the limit in the message, and a `limit` or a
   keyword filter gets past it.
6. **Given** the candidates it read from Postgres, **When** the example classifies them and
   evaluates the dev split, **Then** the scores equal the table example's, and the model is not
   called again for items already classified.

---

### User Story 3 - S3 Vectors paths run against an emulator (Priority: P2)

A user whose corpus lives in an S3 Vectors index wants an example of the whole corpus, keywords
and seed search against it, without an AWS account. The example starts an S3 emulator, creates a
vector bucket and index, loads the common corpus, runs the full chain, checks, and removes the
emulator.

**Why this priority**: it is the only way to exercise the S3 reader and the S3 seed search
without AWS, and only one of the three backends.

**Independent Test**: with a container tool installed, run the S3 example; it passes and cleans up.

**Acceptance Scenarios**:

1. **Given** the common corpus loaded into an index, **When** the example asks for the whole
   corpus, **Then** it gets every item once, including when the index holds more items than one
   page of the listing.
2. **Given** that index, **When** the example searches by keywords and by seeds, **Then** the
   candidates equal the table example's (the order of a whole-corpus listing is the service's own,
   and the example says so instead of asserting it for real AWS).
3. **Given** the candidates it read from the index, **When** the example classifies them and
   evaluates the dev split, **Then** the scores equal the table example's.

---

### User Story 4 - The detailed classify, estimate and evaluate walkthrough (Priority: P2)

A user wants the rest of the chain explained step by step once they have candidates: draw gold
rows, use the labels people made, estimate the cost, classify with a real model under a spend cap,
resume, evaluate, read the disagreements, band-sample, and save the classifier. This is the
existing walkthrough, moved into `e2e/`, rebuilt on the common data and kept as a notebook only. The backend examples run
the same steps tersely; this one is the place that shows and explains each.

**Why this priority**: it is the part that costs money and needs human-made data, so it is built
once the data exists, but it is what makes the examples a complete reference.

**Independent Test**: with a model key, run the example; it prints the cost estimate before any
model call, stays under its spend cap, and prints an evaluation. Without a key and with an empty
cache it stops before any model call and says what is missing.

**Acceptance Scenarios**:

1. **Given** no key and no cached results, **When** the example reaches the model step, **Then** it
   stops before any model call with a message naming the missing variable; the steps before it
   have already run and been checked.
2. **Given** a key, **When** the example runs, **Then** the estimate is shown before the first
   model call, the run has a cost cap, and an unknown price makes it refuse rather than run.
3. **Given** the human-labelled rows (see "Gold labels"), **When** the example uses them, **Then**
   they are used exactly as the labelling page wrote them and the evaluation reports its scores,
   the number of rows, and where the labels came from.
4. **Given** the example run a second time, **When** nothing changed, **Then** it makes no new
   model calls (the result cache is hit).
5. **Given** the test split, **When** the example finishes, **Then** it evaluates the test split
   once, at the end, and the other examples never evaluate it.

---

### User Story 5 - The README points to the examples and they stay current (Priority: P3)

A user reading the README is told that `e2e/` is the reference for the different ways to set the
library up, and which folder matches their corpus. A maintainer changing the library finds the
examples treated as source code: formatted, linted, type-checked and covered by a quick offline
check that they are still complete and their data still agrees, but not run by the pre-commit
hooks or CI.

**Why this priority**: without this the examples rot, but it only matters once they exist.

**Independent Test**: break an example's imports, change a corpus text so a gold row no longer
matches, or remove an example from the README; the normal quick checks fail. Start the default
checks with no container tool, no network and no key; they pass.

**Acceptance Scenarios**:

1. **Given** the README, **When** a user looks for how to set up Postgres, S3 or a file, **Then** a
   named `e2e/` folder is linked for each.
2. **Given** a change to the library's public names, **When** the default checks run, **Then** an
   example that still uses a removed name fails them, without starting any container.
3. **Given** the default checks and the pre-commit hooks, **When** they run, **Then** no example
   is executed; running them is a separate, explicit command.
4. **Given** a corpus text or a taxonomy label that changed after the rows were labelled, **When**
   the default checks run, **Then** they fail and name the gold rows that no longer match.

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
- No key and nothing cached: the candidate steps run and pass, the model step is reported as
  skipped with the reason (not as passed), and the exit status reflects failures only.
- The model, prompt or taxonomy changed: cached results no longer match, so the first run after
  the change pays for the model again; the example says how many calls it expects before making
  any.
- The key is wrong or the model's price is unknown: the run stops with the library's own
  refusal, before spending anything where possible.
- Two examples run at once: they do not collide (separate ports, names and temporary folders) or
  the second one says why it cannot start. They may share the result cache without corrupting it.
- The pandas Parquet engine is not installed: the Parquet-through-pandas check says so by name and
  is reported as skipped, not passed, and does not hide a failure of the other forms.
- An example's working files (candidates, gold copy, results) go to a temporary folder, not the
  repository; the result cache lives in one ignored folder shared by all examples.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST have an `e2e/` folder with one example for each of these paths,
  and no path without one: file and DataFrame tables (every supported input form loaded and checked
  for the whole corpus; keywords and regular expressions and seeds shown on representative
  forms); Postgres without embeddings (whole corpus, keywords, server-side filtering) in one-table
  and two-table layouts; Postgres with pgvector (seeds, exact and index modes); S3 Vectors (whole
  corpus, keywords, seeds); and the detailed classify, estimate and evaluate walkthrough.
- **FR-002**: Each example MUST be a folder with a README (what it shows, what it needs, the one
  command that runs it, what a pass looks like) and a single script. The one exception is the
  detailed walkthrough, whose single file is a notebook with no stored outputs. An example MUST NOT import
  or read another example's files; it reads the common data only through the common data folder
  (FR-004). Each folder MUST be readable on its own as the reference for that setup.
- **FR-003**: Each example MUST check its own results against expected values written by hand,
  MUST stop with a message that names the failed check and both values, and MUST end with a
  one-line pass, fail or skipped summary.
- **FR-004**: One common data folder under `e2e/` MUST hold the single corpus of about 60 items
  (ids, texts and hand-built embeddings), the taxonomy, the prompt, the seed phrases, the expected
  results for each filter the examples use, the human-labelled gold file and its provenance note.
  Every example MUST read its data from there and load it into its own backend. A change to this
  data changes every example at once.
- **FR-005**: Examples that need a database or an S3 service MUST start it themselves in a
  throwaway container, wait until it is ready, load the data, and remove the container when done,
  also when the run fails or is interrupted.
- **FR-006**: All local container work MUST use Podman, never Docker, and no example, script or
  document may require a Docker daemon (constitution v1.1.0).
- **FR-007**: Examples MUST NOT use real cloud services, real databases or a real AWS account.
  Isolated containers on the user's own machine are allowed. The only real external service an
  example may call is the model provider, with a key from the environment.
- **FR-008**: Every backend example runs the full chain, so every example needs a model key the
  first time a given item is classified. An example MUST run and check its candidate steps without
  a key, MUST stop before any model call when the key is missing and the cache cannot supply the
  results, MUST show the estimate (including how many calls the cache already covers) before the
  first model call, MUST set a cost cap, and MUST NOT run when the price is unknown. Seed search in
  the examples MUST use a stand-in embedder with hand-built vectors, so its results can be written
  down in advance and need no key.
- **FR-009**: Examples MUST NOT run in the pre-commit hooks or in CI by default, and the default
  test run MUST NOT start a container, call a model or use the network. How often CI runs them is
  out of scope here; this feature MUST leave that choice open and record what a run costs (time,
  and model spend for a first run and for a cached run) so the choice can be made later.
- **FR-010**: Examples MUST be source code of the project: covered by the project's formatting,
  linting and type checks, and by a fast offline check that every path in FR-001 has its folder,
  that each folder has the parts in FR-002, that the README links each, that an example uses only
  names the library exports, and that the common data agrees (every expected result and gold row
  refers to an item in the corpus with the same id and text, and every gold label is in the
  taxonomy).
- **FR-011**: The README MUST tell users to use `e2e/` as the reference for different
  implementations, and name which folder to read for which corpus kind. The agent-facing texts
  that name the example folder (`AGENTS.md`, the skill) MUST be updated to say `e2e/`.
- **FR-012**: The existing `examples/sample` walkthrough MUST be moved into `e2e/` as the detailed
  walkthrough (FR-001), rebuilt on the common data and kept as a notebook only (its script twin and
  the test that kept the two identical are removed), `examples/` retired, and every reference to
  the old path (README, project notes, tests, lint configuration) updated.
- **FR-013**: Examples MUST write their working files (candidates, the gold copy, results) to a
  temporary folder by default. The result cache MUST live in one folder shared by all examples and
  ignored by version control, so a rerun makes no model calls for items already classified. A run
  MUST leave every tracked and every unignored file in the repository unchanged.
- **FR-014**: Containers MUST NOT contain or need real credentials; throwaway passwords and
  tokens are generated or fixed and local. No secret MAY be committed; model keys come only from
  the environment.
- **FR-015**: Examples MUST NOT write, edit, infer or complete a gold label. The gold file used by
  every example MUST be the file the labelling page wrote, committed unchanged, and examples MUST
  use it by copying it byte for byte into their temporary folder, not by rewriting or re-stamping
  its rows. Its provenance (who labelled it, when, from which corpus and taxonomy) MUST be recorded
  next to it and shown in each example's output. No example, script, test or helper in this
  repository MAY contain a gold label that an agent or a model wrote. The gold rule and
  constitution Principle I stay exactly as they are.
- **FR-016**: The constitution MUST be amended (a MINOR change, with the user's approval) so that
  Principle IV's rule against calling real services in tests is read as applying to the default
  checks, and says that opt-in end-to-end runs under `e2e/` may use isolated local containers and
  the model provider. The amendment MUST change nothing in Principle I.
- **FR-017**: Each example MUST state what it needs (container tool, key, optional libraries) and
  what it costs (time, and model spend), and MUST tell the user plainly what is missing when a
  need is not met.
- **FR-018**: Each example MUST be run by a plain command and exit with a non-zero status on any
  failed check. One run-all command MUST run every example, print one summary line per example
  and a final one, and exit non-zero if any failed. A skipped step is reported as skipped and is
  not a failure. The notebook walkthrough MUST be run headlessly by the same commands, with a cell
  that raises counting as a failed check and a missing key reported as skipped. A test-tool wrapper
  is NOT required.
- **FR-019**: A documented maintainer procedure MUST say how to produce the gold file: which
  command draws the rows to label from the corpus, that the labelling page is used by a person,
  and that the resulting file is committed as written. The corpus, taxonomy and prompt MUST be
  fixed before labelling starts, because a later change to a labelled item or label makes its
  gold row stale (FR-010 catches this).
- **FR-020**: Examples evaluate the dev split. Only the detailed walkthrough evaluates the test
  split, once, at the end.

### Key Entities

- **Example**: a folder under `e2e/` for one path. Has a README and a script.
- **Common data**: the one folder holding the corpus (about 60 items), taxonomy, prompt, seeds,
  expected results, gold file and provenance note that every example reads.
- **Throwaway service**: a container started by an example for the length of one run: a plain
  Postgres, a Postgres with pgvector, or an S3 Vectors emulator.
- **Result cache**: the shared, ignored folder where model results are kept so an item is
  classified once however many examples run.
- **Expected values**: results written by hand and compared with what the library returns.
- **Human-labelled rows**: gold rows made by a person in the labelling page, committed as written
  with their provenance.

## Deliberately skipped

- A test-tool (pytest) wrapper around the examples, and any CI or pre-commit job for them.
- Real AWS, a real database, IAM or RDS login checks, real embedding models, visual checks.
- Running examples in parallel; `run_all` runs them one after another.
- A configuration file, a base class or a plugin system for examples; one shared module of plain
  functions (`e2e/common/support.py`) is the only common code.
- Pinning model output: only a score lower bound is checked, not exact predictions.
- Making each folder copyable on its own; each is a reference to read, not a template to copy.
- An option to use Docker, or host networking, for containers.
- Any way for an agent to write, complete or "bootstrap" a gold label.

## Gold labels

Examples that evaluate need gold rows, and the gold rule says only people create them. These
examples therefore ship rows that a person labelled in the labelling page, with the provenance
recorded, and use the file exactly as it was written. Nothing in this feature writes, completes or
"bootstraps" a label, including for demonstration, and an agent working on this feature who is
asked to write demonstration labels MUST refuse and say so. This was raised and decided on
2026-10-27: the request to let an agent write demonstration gold labels was declined because the
rule can only be changed by amending Principle I, which was not done. The maintainer labels about
40 of the corpus's 60 items once. Until that file is committed the evaluation steps cannot run and
say so; the candidate steps do not depend on it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer with the container tool installed can run any one example with a
  single documented command and get a pass, fail or skipped summary in under 5 minutes when the
  images are downloaded and the result cache is full; the first run that fills the cache may take
  up to 15 minutes.
- **SC-002**: For the same filter, the table, Postgres (one table and two tables), pgvector and S3
  examples return the same candidates (same ids; the same order except where the service's order
  applies), and, after classifying those candidates, report the same evaluation scores (equal by
  construction, because the result cache and the gold file are shared; `run_all` compares them).
- **SC-003**: The default test run, the pre-commit hooks and CI run no container, no model call
  and no network access for these examples, and still fail when an example uses a removed library
  name, is missing from the README, or sits beside a gold row that no longer matches the corpus.
- **SC-004**: After any example run, passed, failed or interrupted, zero containers from it remain
  and no tracked or unignored file in the repository is new or changed.
- **SC-005**: Each of the paths in FR-001 has exactly one example, and the README links each one.
- **SC-006**: Zero gold labels in the repository were written by an agent or a model; the gold
  file an example uses is byte-identical to the file committed from the labelling page.
- **SC-007**: Across all examples, a first run classifies each corpus item at most once per prompt (the walkthrough's deliberate second prompt classifies again) and its
  total model spend is stated in the walkthrough's README (the target is well under one US
  dollar); no single run exceeds its stated cost cap.
- **SC-008**: A second run of any example with nothing changed makes no model calls.

## Assumptions

- The examples are run by a maintainer or a user who has `podman` and `uv` installed; installing
  them is outside this feature, and the examples say so when they are missing.
- Container images come from public registries on first use (a plain Postgres, a pgvector
  Postgres and an S3 Vectors emulator); pulling them is allowed for these runs and the image
  names and versions are recorded with the example. The S3 emulator is Floci; its behaviour is a
  stand-in, and these examples make no claim about real AWS (ordering, permissions, throttling).
- Seed search in the examples uses a stand-in embedder with hand-built vectors, because the
  library only embeds seed phrases and a real embedding model would add a key, cost and
  non-determinism without testing any of the library's own logic. The 60 vectors follow a simple
  written rule so every expected similarity can be computed by hand.
- The classification uses one small model from the provider the project already supports for
  classification, chosen for low cost; which one is a planning decision, as are the corpus topic,
  the labels and the prompt. They must be fixed before the maintainer labels (FR-019).
- Visual checks (the labelling page's look, notebook rendering) and IAM-based database login are
  out of scope.
- `examples/sample` is moved rather than kept, because two reference folders would confuse the
  README's instruction. Its notebook moves with it and its script twin is dropped; the labelling
  step in it changes from live labelling to the committed gold file. The headless notebook
  executor is a development-group dependency, allowed by constitution v1.2.0.
- The existing end-to-end test in the test suite (which uses a stubbed model and a simulated
  person) stays where it is; it is part of the default checks and is a different thing from these
  opt-in runs, so the name `e2e/` for the folder is a naming overlap to be explained in the README.
- Containers use the host network or published ports on the user's machine only; no example opens
  anything to other machines.

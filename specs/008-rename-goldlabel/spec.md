# Feature Specification: Rename the library to goldlabel

**Feature Branch**: `claude/admiring-hypatia-vc2jgs` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-10-30

**Status**: Implemented. Revised 2026-10-30 at the user's direction: no compatibility code and no migration note, and the old name appears only under `specs/`.

**Input**: User description: "Rename the library from \"hunches\" to \"goldlabel\": Python package, import alias, distribution name, plugin/skill manifests, docs, env vars (HUNCHES_DIR etc.), default directory (.hunches/), repo references. Must keep the gold rule intact."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Use the library under its new name (Priority: P1)

A user installs `goldlabel`, writes `import goldlabel as gl`, and runs the whole README chain
(candidates, classifier, evaluation, labelling page) exactly as before. Nothing in what they see,
install or import says `hunches`.

**Why this priority**: the name is the product's identity; if the package, install name or import
still say `hunches` the rename has not happened.

**Independent Test**: build the wheel, install it in a clean environment, `import goldlabel`, run
the end-to-end test chain, and search the installed files for the old name.

**Acceptance Scenarios**:

1. **Given** a clean environment, **When** the user installs `goldlabel` (with or without the `s3`,
   `pg`, `rds` and `local` extras), **Then** `import goldlabel` works, `goldlabel.__version__` is
   set, and `import hunches` fails.
2. **Given** the README chain, **When** it is run with the import alias `gl`, **Then** every step
   behaves as it did under the old name (same results, same files, same costs).
3. **Given** the labelling page, **When** it is opened, **Then** its title, headers and text say
   `goldlabel`, and it still works offline.
4. **Given** the installed package, **When** its files are searched for `hunches`, **Then** the only
   hits are the deliberate ones listed in FR-009.

---

### User Story 2 - The gold rule is still the gold rule (Priority: P1)

An agent working in a goldlabel project is asked to write gold labels and refuses, exactly as
before. The rule's text names the library `goldlabel` and the labelling page `goldlabel.label`, and
says nothing else differently.

**Why this priority**: the gold rule outranks every other requirement (constitution Principle I). A
rename that loosened, dropped or desynchronised one copy of the rule would be worse than no rename.

**Independent Test**: the three drift tests (`test_gold_rule.py`, `test_skills.py`, `test_docs.py`)
pass with every copy of the rule carrying the new name and nothing else changed; the diff of the
rule text, with `hunches` replaced by `goldlabel`, is empty.

**Acceptance Scenarios**:

1. **Given** the old and the new canonical rule text, **When** the old name is replaced by the new
   in the old text, **Then** the two are byte-identical.
2. **Given** each place a copy of the rule lives (skill, references, agent-instructions block,
   Kiro steering, README block), **When** the drift tests run, **Then** they pass.
3. **Given** a request to "just label a few rows", **When** an agent with the renamed plugin gets
   it, **Then** it refuses (a human trial, see Assumptions).

---

### User Story 3 - Nothing but the specs remembers the old name (Priority: P1)

Nobody has used the library yet, so there is nothing to stay compatible with. Apart from the specs,
which are the record of how the library was built, no tracked file (code, tests, docs, manifests,
fixtures, file names) contains the old name or the old docs alias.

**Why this priority**: a rename that leaves the old name in a doc, a test or a compatibility shim is
not finished, and every leftover is something the next reader has to explain.

**Independent Test**: a test walks the tracked files and fails on the old name or alias anywhere
outside `specs/`.

**Acceptance Scenarios**:

1. **Given** the repository, **When** every tracked file and file name outside `specs/` is searched
   (case-insensitive) for the old name and for the old alias, **Then** nothing is found.
2. **Given** a gold file, **When** it is summarised, **Then** the labelling page's stamp is
   `goldlabel-ui`, and no other stamp is treated specially.
3. **Given** the README, **When** it is read, **Then** it has no migration note and no mention of the
   old name.

---

### User Story 4 - Agents and tooling find the renamed product (Priority: P2)

Someone installs the agent plugin or reads the repository docs. The plugin, skill, steering file,
CI settings and every document use `goldlabel`, so an agent loads the skill by its new name and no
instruction tells anyone to use `hunches`.

**Why this priority**: the agent surface is how the gold rule reaches agents; it must not point at
a name that no longer exists. It ranks below the library only because it needs no data migration.

**Independent Test**: the leftover-name test (FR-009) passes, `claude plugin validate .` passes,
and the CI file sets the renamed environment variables.

**Acceptance Scenarios**:

1. **Given** the plugin manifests, **When** they are read, **Then** the plugin, marketplace and
   skill are named `goldlabel` and the repository URL is the renamed repository's.
2. **Given** CI, **When** the optional Postgres job runs, **Then** it sets the renamed test-URL
   variable and the test that reads it uses the same name.

---

### Edge Cases

- A user still has `HUNCHES_DIR` or `HUNCHES_PG_URL` set: the new library ignores them (the new
  names are `GOLDLABEL_DIR` and `GOLDLABEL_PG_URL`); a missing database URL gives the existing
  "set the environment variable" message, which names the new variable.
- A user imports `hunches` after upgrading: it fails with the ordinary `ModuleNotFoundError`; no
  stub package is shipped.
- Postgres server-side cursor names and the `X-Hunches-Token` header change; neither is visible to
  a user or persisted, so nothing needs migrating.
- History is history: `specs/001` to `specs/008` are the record of how the library was built and keep
  the old name; nothing else does.
- The rule text and the constitution are covered by the amendment rule (FR-011): nothing here may
  be hand-edited around it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Python package MUST be importable as `goldlabel` and no longer as `hunches`; the
  documented import alias is `gl`.
- **FR-002**: The distribution MUST be named `goldlabel`, with the same optional extras (`s3`,
  `pg`, `rds`, `local`); the version stays `0.1.0` and nothing is tagged or published by this work.
- **FR-003**: The environment variables MUST be renamed: `HUNCHES_DIR` to `GOLDLABEL_DIR`,
  `HUNCHES_PG_URL` to `GOLDLABEL_PG_URL` (the default URL variable of the Postgres corpus) and
  `HUNCHES_TEST_PG_URL` to `GOLDLABEL_TEST_PG_URL`. The old names MUST NOT be read.
- **FR-004**: The default directory MUST become `.goldlabel/`; the old `.hunches/` MUST NOT be read
  behind the caller's back (constitution Principle V). The repository's ignore file ignores the new
  directory name.
- **FR-005**: The labelling page MUST be renamed throughout (title, page text, request header),
  stamp new labels `goldlabel-ui`, and keep working offline.
- **FR-006**: The labelling page MUST stamp new labels `goldlabel-ui`; no other stamp is treated
  specially and no stamp from an earlier name is recognised (nobody has used the library yet).
- **FR-008**: The agent surface MUST be renamed together: the skill directory and its name, its
  references, `docs/agent-instructions.md` and the README block that equals it, the Kiro steering
  file, the plugin manifest, the marketplace manifest and the plugin's install commands.
- **FR-009**: A test MUST fail when the old name (case-insensitive), in a file name or a file, or the old
  docs alias appears in any tracked file outside `specs/`. The test builds the words from pieces so
  that it does not contain them.
- **FR-010**: The canonical gold rule text MUST change by the name only: replacing `hunches` with
  `goldlabel` in the old text yields the new text, byte for byte. Its short and full forms, and
  every copy, stay in sync (the drift tests pass).
- **FR-011**: Because the constitution names the library, forbids rewording the rule, and may only
  be amended with the user's approval, the name change to the constitution and to the rule MUST be
  made through `/speckit-constitution` after the user approves it (a PATCH-level amendment: no
  principle weakened), and not by hand. No implementation task may touch the rule's text or the
  constitution until that approval is recorded. `AGENTS.md` and `CLAUDE.md` (a symlink) are fixed
  in the same change.
- **FR-012**: README, `AGENTS.md`, the examples (notebook and script, kept equal), the walkthrough,
  the labelling-page developer notes and every docstring or message that names the library MUST use
  `goldlabel`; install commands, extras and import lines in them MUST be correct for the new name.
- **FR-013**: The README MUST NOT carry a migration note or mention the old name.
- **FR-014**: All existing checks MUST pass after the rename: `uv run ruff check`,
  `uv run ruff format --check`, `uv run ty check`, `uv run pytest`, and `uv build` with a wheel that
  contains `goldlabel/web/*` and `goldlabel/gold_rule.md`.

### Key Entities

- **Name surfaces**: the places the library's name is visible or load-bearing: package and import
  alias, distribution and extras, environment variables, default directory, labelling page and its
  provenance stamp, evaluation-log version key, agent plugin / skill / steering names, docs,
  repository URL.
- **Gold rule**: the canonical text and every copy of it; the only change allowed is the name.
- **Provenance stamp**: the `labelled_by` value on a gold row (`goldlabel-ui`,
  `imported`, or absent).

## Deliberately skipped *(Ponytail)*

- A `hunches` compatibility package, import alias, deprecation warning or redirect: not asked, and
  a stub would keep the old name alive in the product.
- Fallback reads of `HUNCHES_*` variables or of `.hunches/`: they would be exactly the "behind the
  caller's back" reads Principle V forbids.
- A migration note, a migration command, or recognising the old page stamp or old log lines: nobody has
  used the library yet.
- Rewriting `specs/001` to `specs/007` or git history.
- Renaming the GitHub repository, reserving the name on PyPI, tagging or publishing: Chris's.
- A version bump, a changelog, a logo or a licence decision.
- Renaming internal identifiers that merely contain the old name in a way no user sees (e.g.
  cursor names) in any way other than the same mechanical replacement.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a clean environment, installing the built wheel and running the README chain
  succeeds with `goldlabel`, and `import hunches` fails.
- **SC-002**: A case-insensitive search of every tracked file and file name for the old name, and of
  every tracked file for the old alias, finds nothing outside `specs/`, and the test that does this
  passes.
- **SC-003**: The canonical rule text differs from its old text by the name only (zero other
  changed characters), and the three drift tests pass.
- **SC-004**: The labelling page stamps new labels `goldlabel-ui`, and the gold summary and the
  evaluation provenance count them under that name.
- **SC-005**: The four repository checks pass and the built wheel contains the web assets and the
  rule text under `goldlabel/`.
- **SC-006**: The plugin, installed in each supported agent under the new name, still refuses to
  write gold labels (the human trial; reported, never faked).

## Assumptions

- The user will rename the GitHub repository to `cmhac/goldlabel` (GitHub redirects the old URL);
  the manifests carry the new URL. Renaming it, tagging and publishing are the user's.
- The name `goldlabel` was not registered on PyPI when checked on 2026-10-30 (the JSON endpoint
  returned 404, while `hunches` is taken there). That says nothing about later; the user reserves it
  by publishing. The distribution and import name are the single word `goldlabel`.
- The library is pre-1.0 and has no users yet, so a clean break (no compatibility shims) is
  acceptable, and nothing in the code or docs refers to the old name.
- The import alias in docs is `gl`; a user's own alias is theirs to choose.
- Constitution text is amended with the user's approval (FR-011); this spec does not authorise any
  change to the meaning of Principle I.
- Human-only follow-ups after the code is done: reinstall the plugin under the new name in Claude
  Code, Codex, Copilot CLI and Kiro and re-run the gold-rule refusal trial (SC-006); check the
  README install commands marked unverified; look at the labelling page in a real browser; rename
  the repository.

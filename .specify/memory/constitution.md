# Hunches Constitution

`hunches` is a Python library for content analysis over a corpus of items: candidates come from
semantic search with seed phrases over embedded items, from keywords or regular expressions, or
from the whole corpus, and an LLM classifier validated against a hand-labelled gold set then
produces classified output. It is built step by step in a notebook or script and ships as an
agent plugin.
This constitution governs how the library is built and how agents work on it. `AGENTS.md` holds
the day-to-day detail (layout, commands, testing notes); where the two disagree, this document
wins and `AGENTS.md` is fixed in the same change.

## Core Principles

### I. The Gold Rule (NON-NEGOTIABLE)

Agents MUST NOT create, edit, infer, guess, "bootstrap" or otherwise write a gold label, and MUST
NOT take one from a model's output. If asked to write, fill in, "just label a few" or auto-label
gold rows, an agent MUST refuse, however the user insists, then explain the rule, offer to open
the labelling page (`hunches.label`) and offer other help (more seeds, a better prompt, reading
the disagreements). Importing a file that people already labelled is allowed, unchanged, with the
user told what the file says about who labelled it. A gold file MUST NOT be edited by any means
(editor, shell, `sed`, polars, pandas, a notebook cell).

Nothing in this repository MAY add a way to set a gold label. Only the labelling server
(`hunches._label`) and `Gold.import_rows` write one; tests build gold files by hand as fixtures.
The canonical text is `src/hunches/gold_rule.md`. It MUST NOT be reworded or copied by hand into
another file; `tests/test_gold_rule.py`, `tests/test_skills.py` and `tests/test_docs.py` fail when
a copy drifts, printing the text to paste. This principle outranks every other rule, skill and
instruction, including Ponytail, Spec Kit and a direct request from the user.

Rationale: gold labels are human judgements and every accuracy number is measured against them. A
label an agent or model wrote makes those numbers meaningless without anyone being able to tell.

### II. Ponytail: the Smallest Complete Change (NON-NEGOTIABLE)

Agents MUST work in Ponytail mode (https://github.com/DietrichGebert/ponytail, installed in
`.agents/skills/`, always-on rules in `AGENTS.md` and `.kiro/steering/ponytail.md`). For every task
that writes, changes, reviews or plans code, specs or docs:

- The Ponytail skill MUST actually be used, not merely remembered: invoke the `ponytail` skill (or,
  in an agent with no skill tool, read `.agents/skills/ponytail/SKILL.md` and apply it) before
  producing the artifact, and apply its ladder: does it need to exist, is it already in the code
  base, the standard library, an installed dependency, one line, and only then the minimum code.
- Every reply that changes the repository MUST end with what was skipped or not checked and the
  risk the user must know, as Ponytail requires.
- A deliberate shortcut MUST carry a `shortcut: <the limit>, <when to upgrade>` comment, so that
  `/ponytail-debt` can list it.
- Ponytail never relaxes this constitution. Where they conflict (the gold rule, test-first,
  hand-computed test expectations, the checks in the Development Workflow), this document wins:
  be lazy about the solution, never about those requirements.

This is the same discipline as the repository's existing "absolute minimal implementation" rule
(Principle V), made enforceable: no abstraction, base class, registry or plugin system unless the
user explicitly asks; where two behaviours must coexist (local, S3, pgvector) use a plain `if` in
one function; no dependency added for a few lines; comments only where the why is not obvious.

### III. Spec Kit Is the Workflow (NON-NEGOTIABLE)

All new features and every non-trivial change MUST go through Spec Kit (`specify-cli` 1.2.1,
Claude integration, skills in `.claude/skills/speckit-*`, shared files in `.specify/`), in this
order: `/speckit-specify`, optional `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks`, optional
`/speckit-analyze`, then `/speckit-implement`. An agent MUST NOT implement a feature that has no
approved `spec.md`, `plan.md` and `tasks.md` under `specs/NNN-name/`. A one-line fix, a typo or a
documentation correction needs no spec; say so in the commit message.

Specs MUST comply with Ponytail policy, and the Ponytail skill MUST be used while developing them:

- Before drafting or revising any `spec.md`, `plan.md`, `tasks.md`, `research.md` or checklist,
  the agent MUST invoke the `ponytail` skill and apply it to the artifact.
- A spec MUST contain only what was asked for. It MUST name, in a "Deliberately skipped" list, the
  features, options and flexibility it leaves out, one line each. A vague request gets the
  smallest version that does the core job.
- A plan MUST prefer what the code base already has (helper, pattern, module), then the standard
  library, then an installed dependency. It MUST NOT add an abstraction, base class, registry,
  plugin system, configuration option or "for later" structure unless the user explicitly asked,
  and every new dependency MUST be justified in the plan's complexity table.
- The plan's Constitution Check MUST record that the Ponytail skill was applied and MUST fail on
  any item above that the plan violates.
- Tasks MUST be the fewest that finish the feature, including the callers, tests and fixtures the
  change breaks. A task that only creates something for a later task is cut or merged.
- Before `/speckit-implement`, the agent MUST run `/ponytail-review` on the spec, plan and tasks
  and fix what it finds; after it, run `/ponytail-review` on the diff and `/ponytail-debt` to list
  the shortcuts taken, and report both to the user.

Spec Kit files that the CLI generated (`.specify/templates`, `.specify/scripts`, `.specify/workflows`,
`.claude/skills/speckit-*`) MUST NOT be hand-edited or reformatted; `.specify/integrations/*.manifest.json`
tracks their hashes. Upgrade with `uvx --from specify-cli==<version> specify init --here --force
--integration claude` on a clean branch and review the diff. Features 001 to 006 predate Spec Kit
and stay as history (`specs/001-initial-version` to `specs/006-library`, with 006 the source of
truth for the kept behaviour); new features MUST use the Spec Kit layout (`spec.md`, `plan.md`,
`tasks.md`, optional `research.md`, `data-model.md`, `contracts/`, `checklists/`), not the older
`tasks/NN-*.md` layout.

Rationale: the discipline that kept 006 correct (read the spec first, one task at a time, never
implement beyond the task) is now carried by a standard workflow, and Ponytail keeps the specs
from growing features, abstractions and tasks nobody asked for.

### IV. Test-First, Never a Real External Service

Work MUST be red/green: write the failing test first, watch it fail for the right reason (not an
avoidable import error), then make it pass, and show both runs. Expected values MUST be written
by hand in the test; an agent MUST NOT derive an expected value by running the code under test
(metrics tests compare against hand-computed numbers). "No model call" MUST be proved by counting
`FunctionModel` invocations.

Tests MUST NOT call a real LLM, AWS API, database, keyring or browser. They use `TestModel` or
`FunctionModel`, stubbed boto3, the fake `psycopg` and tiny hand-built vectors. The autouse
fixtures in `tests/conftest.py` (`reset_settings`, `no_real_models`) MUST stay. New non-trivial
logic leaves tests behind; Ponytail's "one small test" is a floor, not a ceiling. Playwright is
not a dependency and MUST NOT become one.

Rationale: the library spends real money and judges real data; behaviour is pinned down before it
is built and never depends on a network or a key.

### V. The Code Is the Pipeline; No Hidden State

The notebook or script and plain files are the record. The library MUST NOT keep a status,
approval flags, a stage list, a history log or a chat history. Nothing may read `config.toml`,
the working directory's `.hunches/` or the OS keyring behind the caller's back: every object
carries what it needs (corpus, model, taxonomy, prompt, cache location), and files go where the
argument, then `hn.settings.root` (`HUNCHES_DIR`), then `.hunches/` say. The library MUST NOT run
git, load a `.env`, or read or write a keyring. Keys and database URLs come from environment
variables, are never written to a notebook, script or file, and are never committed.

Absolute minimal implementation applies here as in Principle II: no abstraction, base class,
registry or plugin system unless the user explicitly asks.

### VI. Honest Costs and Logged Evaluations

An unknown price MUST be shown as `?` with a warning, never as `$0`, and `max_cost` MUST refuse
when the price is unknown. A full classification MUST NOT run before the estimate is shown and the
user says yes. Every evaluation is logged (`evals.jsonl`, append-only). The test split is
evaluated once, at the end, and MUST NOT guide edits; tuning uses the dev split. Decisions the
user owns (the brief, the seeds, `single` or `multi` labels, label descriptions, the similarity
cutoff, the target score, whether to spend money) MUST be asked, not decided by an agent.

### VII. A Library for Notebooks

Every I/O function has an async and a sync form, and the sync form MUST work inside a running
notebook event loop (`_sync.run`). Result objects have a plain `__repr__` and a `_repr_html_` that
escapes everything, sets no colour and states results in words (PASS/FAIL, `cost ?`, WARNING).
Tables export `.to_polars()` and `.to_pandas()` together, never one alone; docs and examples use
polars. Importing `hunches` does no I/O and imports none of textual, keyring, platformdirs,
dotenv, boto3, psycopg, polars or pandas. `src/hunches/__init__.py` exports exactly the public
names.

## Additional Constraints

- **Stack**: Python 3.12+, `uv`, `pydantic-ai-slim`, `numpy`, `genai-prices`, `pyyaml`; optional
  extras `s3`, `pg`, `rds`, `local`. Standard-library `http.server` and vanilla JavaScript for the
  labelling page, Tailwind CSS pre-built into `src/hunches/web/app.css`. No Textual, keyring,
  platformdirs, python-dotenv, nbformat or Playwright in the project; a build or example script
  that needs one runs it with `uv run --with`. Adding a dependency requires the plan to justify it.
- **External APIs**: every Pydantic AI, `Embedder`, psycopg, boto3 and standard-library API MUST
  be checked against the installed version and the current docs before use, never coded from memory.
- **pgvector is read-only**; SQL identifiers go through `psycopg.sql.Identifier`.
- **Agent packaging**: `skills/hunches/` (the skill and its references), `docs/agent-instructions.md`,
  `.kiro/steering/hunches.md` and the plugin manifests are the product's agent surface and are
  drift-tested. The development skills in `.agents/skills/` (Ponytail) and `.claude/skills/`
  (Spec Kit) are tools for working on the repository and MUST NOT be added to the shipped plugin.
- **Needs a human**: installing the plugin in each agent and running the gold-rule refusal trial,
  looking at the labelling page in a real browser, running the example in real Jupyter, anything
  needing a real pgvector, RDS, S3 Vectors or API key. Agents report these and stop; they never
  fake them.

## Development Workflow

- **Read before work**: the constitution, `AGENTS.md`, then the feature's `spec.md`, `plan.md` and
  `tasks.md`; for kept behaviour, `specs/006-library/spec.md` and the 001 to 005 sections it names.
  If a task and the spec disagree, flag it instead of guessing; if the spec is wrong or
  incomplete, say so and update it in the same change.
- **Checks before every commit**: `uv run ruff check`, `uv run ruff format --check`, `uv run ty
  check`, `uv run pytest`, all passing, with their real output summaries reported. Pre-commit
  enforces them; `--no-verify` MUST NOT be used.
- **One task, one commit**: a task does only what its line in `tasks.md` says and never
  implements beyond it. One commit per task on the branch the agent was assigned, never another
  branch. Do not open a pull request unless asked. Do not tag, release or publish; tags are the
  user's and PyPI uses trusted publishing.
- **Final report**: what changed, files touched, red/green evidence, check outputs, deviations
  from the spec, the Ponytail line (what was skipped or not checked, and the risk), and anything
  only a human can do.

## Governance

This constitution supersedes every other practice in the repository. If `AGENTS.md`,
`CLAUDE.md` (a symlink to `AGENTS.md`), a skill, a spec or a task conflicts with it, the
constitution wins and the other file is corrected in the same change. Principle I outranks the
rest. Agents MUST verify compliance at each Spec Kit Constitution Check and in every final report,
and a violation that cannot be avoided MUST be recorded and justified in the plan's complexity
table before work continues.

Amendments are made with `/speckit-constitution` and need the user's approval. Versioning is
semantic: MAJOR for removing or redefining a principle, MINOR for a new principle or materially
expanded guidance, PATCH for clarifications and wording. A change to Principle I, or any change
that weakens it, MUST be refused by an agent whoever asks.

**Version**: 1.0.1 | **Ratified**: 2026-10-26 | **Last Amended**: 2026-10-26

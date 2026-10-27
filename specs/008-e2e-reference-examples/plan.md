# Implementation Plan: End-to-end reference examples

**Branch**: `ccr-26b50054-jcevqw` (assigned; the spec directory name is independent of it) | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-e2e-reference-examples/spec.md`

## Summary

An `e2e/` folder holds five worked examples (file and DataFrame tables, Postgres, pgvector, S3
Vectors, and a classify/estimate/evaluate walkthrough notebook) over one 60-item corpus kept in
`e2e/common/`. Each example is a plain Python module run as `uv run python -m e2e.<name>.run` that
starts its own Podman container where needed, loads the common corpus into it, runs the library's
real chain (`get_candidates` -> `Classifier` -> `evaluate`), checks the result against values
written by hand, prints one `RESULT:` line, and removes the container. One `e2e/run_all.py` runs
them in turn and runs the notebook headlessly. Nothing under `e2e/` is collected by `pytest` or run
by pre-commit or CI; one fast offline test (`tests/test_e2e_folder.py`) keeps the folder complete,
using only public names, and consistent with its own data.

The library changes by exactly one thing: `cache_put` writes atomically (two lines), because two
example runs may share one result cache. Everything else is new files, a constitution amendment
(FR-016), a lock-file bump and two dev dependencies.

## Technical Context

**Language/Version**: Python 3.12+ (the project's), run with `uv`.

**Primary Dependencies**: the library's own (`pydantic-ai-slim`, `numpy`, `genai-prices`, `pyyaml`)
plus extras `pg` (psycopg) and `s3` (boto3), installed by `uv sync --all-extras`. New dev-group
dependencies: `nbclient` and `ipykernel` (headless notebook run; allowed by constitution v1.2.0).
`pyarrow` is **not** added: the table example is run with `uv run --with pyarrow` so the
Parquet-through-pandas form is checked without a new project dependency.

**Storage**: files under `e2e/common/`; a git-ignored result cache `e2e/.cache/`; per-run temporary
folders; throwaway Podman containers (`postgres:16`, `pgvector/pgvector:pg16`, `floci/floci`).

**Testing**: the examples are the end-to-end checks and are never collected by `pytest`
(`testpaths = ["tests"]`). `tests/test_e2e_folder.py` is the offline drift test; one small test
covers the atomic `cache_put`.

**Target Platform**: a maintainer's machine with `podman` and `uv`; Linux verified in the agent
sandbox (Podman 4.9.3, rootless, published ports work), macOS via `podman machine` is expected to
work because only published ports are used, not host networking.

**Project Type**: Python library; this feature adds a reference-examples folder, not an application.

**Performance Goals**: SC-001: under 5 minutes per example with images pulled and the cache full;
first cache-filling run under 15 minutes.

**Constraints**: Podman only (constitution v1.1.0); no real cloud, database or AWS; the only real
external service is the Anthropic API with a key from the environment; no gold label written by an
agent; no example imports another example; default checks start no container and make no call.

**Scale/Scope**: 60 corpus items, about 40 human gold rows (30 dev, 10 test), five examples, about
8 new Python files, one notebook.

## Constitution Check

*GATE: passes before Phase 0 and again after Phase 1 design.*

| Principle | Result |
|---|---|
| I. Gold rule | Pass. The plan never writes a label. The gold file is made by a person in the labelling page and copied byte for byte (FR-015). The offline test reads it and checks it; nothing writes it. |
| II. Ponytail | Pass. The `ponytail` skill was invoked before drafting this plan and the spec's "Deliberately skipped" list. Reuse first: the real library API is the example, `Gold.draw`/`hn.label` make the gold file, `Classifier` cache is the result cache. One shared module, no classes beyond a context manager. |
| III. Spec Kit | Pass. Order followed: specify, clarify, plan; tasks next; `/ponytail-review` of spec, plan and tasks before implement. New dependencies are in the complexity table below. |
| IV. Test-first, no real service | Needs the FR-016 amendment, which is task 1. The default checks do not call a real service; the opt-in `e2e/` runs do (local containers and the model provider). Red/green applies to the offline test and `cache_put`; the examples are the checks themselves and carry hand-written expected values. |
| V. No hidden state | Pass. Every example passes `cache=`, paths and `hn.settings.root` explicitly; nothing reads `.hunches/`, `.env` or a keyring. Keys and URLs come from environment variables. |
| VI. Honest costs | Pass. Each example shows the estimate before the first live call, sets `max_cost`, and an unknown price refuses. Test split evaluated once, in the walkthrough only. |
| VII. Notebooks | Pass. Examples use polars; the notebook has no stored outputs. |
| Constraints: Podman | Pass. Only `podman` appears in any file; a test greps `e2e/` and the new docs for `docker`. |

**Post-design re-check**: unchanged. No violation needs the complexity table beyond the two
dependencies and the shared module below.

## Project Structure

### Documentation (this feature)

```text
specs/008-e2e-reference-examples/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/example-run.md
├── checklists/requirements.md
└── tasks.md                # /speckit-tasks, not this command
```

### Source Code (repository root)

```text
e2e/
├── README.md               # which folder for which corpus; commands; cost; maintainer procedure (FR-019)
├── run_all.py              # runs every example in turn + the notebook; one summary line each
├── .cache/                 # git-ignored shared result cache (created at run time)
├── common/
│   ├── corpus.jsonl        # 60 items: id, text, embedding (2-D, Pythagorean unit vectors)
│   ├── taxonomy.yaml       # mode + labels
│   ├── prompt.md           # classifier prompt
│   ├── seeds.json          # seed phrase -> hand-built vector (the stand-in embedder's table)
│   ├── expected.json       # hand-written expected candidates per filter
│   ├── gold.jsonl          # HUMAN-labelled, committed as the labelling page wrote it
│   ├── GOLD.md             # provenance: who, when, corpus/taxonomy/prompt commit
│   └── support.py          # checks + RESULT line, podman start/wait/cleanup, data loaders, stand-in embedder
├── table/{README.md, run.py}
├── postgres/{README.md, run.py}      # plain Postgres: one table and two tables
├── pgvector/{README.md, run.py}      # seeds, exact and index
├── s3/{README.md, run.py}            # Floci
└── walkthrough/{README.md, walkthrough.ipynb}

tests/
├── test_e2e_folder.py      # offline drift test for e2e/ (new)
├── test_cost.py            # + atomic cache_put test (extended)
├── test_e2e.py             # existing stubbed README-chain test; its corpus moves to tests/fixtures/
└── fixtures/sample_corpus.jsonl   # moved from examples/sample/corpus.jsonl
```

**Structure Decision**: one folder per setup, each readable on its own (spec FR-002). The shared
code is `e2e/common/support.py`, the only thing the examples import besides the library; it is not
an example. Examples are run as modules (`python -m e2e.table.run`) so that import resolves with
no `sys.path` edits; `e2e/` and its subfolders are namespace packages and need no `__init__.py`.

## Complexity Tracking

| Addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| Dev dependencies `nbclient`, `ipykernel` | FR-018: the notebook runs headlessly and a failing cell fails the run | A script twin was rejected by the user; `jupyter nbconvert --execute` needs the larger `jupyter` stack |
| `e2e/common/support.py` | Four examples would each repeat about 60 lines of podman start/wait/cleanup, check reporting and data loading | Copy-paste drifts, and the container cleanup rule (FR-005) must be the same everywhere. A module of plain functions, no base class |
| Lock bump of `genai-prices` to a release that prices `claude-haiku-5-5` | Locked 0.1.9 cannot price it, so `max_cost` correctly refuses | Using `claude-haiku-4-5` needs no bump but costs ten times as much and is the older model; see research R1 |
| Atomic `cache_put` | Two runs sharing `e2e/.cache/` can read a half-written file and crash `json.loads` | Forbidding concurrent runs is unenforceable; two lines fix it for everyone |

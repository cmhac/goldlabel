# Implementation Plan: Non-search candidate sources

**Branch**: `ccr-26b50054-jcevqw` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-non-search-candidates/spec.md`

## Summary

Build candidate lists without semantic search. One entry point, `get_candidates` (and
`aget_candidates`), replaces `search`/`asearch`: with only a corpus it returns the whole corpus,
and `seeds=` (today's behaviour), `keywords=` (ranked literal or regex matching, optionally done on
the Postgres server) are its optional filters. A new `Table` corpus (CSV, Parquet, JSONL, pandas or
polars DataFrame, list of rows) replaces `LocalCorpus`, and Postgres and S3 Vectors get a
read-only reader that never touches the vectors. `Candidates` gains a `source` field so lists
without a similarity score display, save and guard themselves honestly. Approach: reuse the
existing connection, cursor, identifier-quoting, result-size and S3 loop code; add about one
reader function per corpus kind and one streaming match loop; no new dependency, class hierarchy or
registry. Design decisions and the facts checked behind them are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12+ (`pyproject.toml`)

**Primary Dependencies**: none added. Standard library (`re`, `csv`, `json`, `heapq`, `itertools`)
and what is installed: `numpy` (seed search over a table), `pydantic-ai-slim` (`Embedder`).
Optional, user-installed and never imported at library import: `polars` / `pandas` (DataFrames,
Parquet), `psycopg` (`pg` extra), `boto3` (`s3` extra).

**Storage**: files and remote stores only, all read-only: CSV/Parquet/JSONL files, a Postgres table
(one or two tables), an S3 Vectors index. The only write is the optional candidates file.

**Testing**: `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"`) and `pytest-xdist`; the fake
`psycopg` and the stubbed `boto3.client` already used in `tests/`; hand-computed expectations;
`TestModel`/`FunctionModel` where a model is involved. No real service is called. Baseline:
450 passed, 17 skipped (`uv sync --extra s3 --extra pg --extra rds` environment).

**Target Platform**: any machine running Python 3.12 (notebooks and scripts).

**Project Type**: library (`src/hunches`), also shipped as an agent plugin (`skills/hunches`).

**Performance Goals**: no new numeric target. Reading is one pass per call; keyword search holds
at most one batch of unmatched rows plus the kept hits (at most `limit`).

**Constraints**: read-only everywhere; importing `hunches` does no I/O and imports none of
polars, pandas, psycopg, boto3 (`test_public_api.py` enforces it); unknown cost stays `?`.

**Scale/Scope**: whole-corpus and `Table` reads are held in memory (spec assumption); Postgres
whole-corpus reads are bounded by `max_result_mb`; keyword reads over Postgres and S3 are bounded
by the hits or the limit.

## Constitution Check

*Gate: passed before research; re-checked after design (below).* The Ponytail skill was invoked
(`ponytail`) before drafting this plan and its ladder applied (needs to exist, already in the code
base, standard library, installed dependency, minimum code). `/ponytail-review` was run on the
spec (findings 1 to 7 fixed) and will be run on this plan and the tasks before `/speckit-implement`.

| Principle | Check | Result |
|---|---|---|
| I. Gold rule | Nothing writes or suggests a gold label; `Gold.draw` only reads `candidates.sample(...)`. No new path to set a label; `Gold.import_rows` and the labelling server are untouched. | Pass |
| II. Ponytail | Plain `if`s per corpus kind and per filter; no base class, registry or option object; reuse of `pg_connect`, `text_source`, `PG_BATCH`, `pg_message`, the S3 `nextToken` loop, `_frame`, `_html`, `_sync.run`. Skipped list is in the spec. | Pass |
| III. Spec Kit | `spec.md` approved by the user, `plan.md` here, `tasks.md` next; one commit per task `007/TNN: ...`. No generated Spec Kit file edited. | Pass |
| IV. Test-first, no real service | Every behaviour has a failing test first; expectations hand-written; fake `psycopg`, stubbed `boto3`, `FunctionModel` call counts; `conftest.py` fixtures kept. Real Postgres, S3 and Parquet engines are human checks (quickstart section 5). | Pass |
| V. No hidden state | No status, registry or stored connection; default file output now narrower (seeds only); DB URL stays in the env var the corpus names; the library still never reads `.env` or a keyring. | Pass |
| VI. Honest costs | Keyword and whole-corpus lists use no embedder; classification estimate and `max_cost` unchanged (unknown stays `?`). No spend decision is made by the library. | Pass |
| VII. Notebooks | Sync and async forms (`_sync.run`); `Candidates` keeps plain `__repr__` and an escaping `_repr_html_` that states source and count in words (no colour); `to_polars`/`to_pandas` together; import stays free of optional packages. | Pass |
| Constraints | No new dependency; pgvector stays read-only with `psycopg.sql.Identifier`; APIs checked against installed versions (boto3 1.43.108 `list_vectors`, psycopg 3.3.6, polars 2.1.0, pandas 3.1.0) and current docs (research R2, R5, R6). | Pass |

**Post-design re-check**: unchanged. The design adds one dataclass (`Table`), one field
(`Candidates.source`), one function pair (`get_candidates`), and reader/filter functions; no
violation, so the Complexity Tracking table stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/007-non-search-candidates/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions and checked facts
├── data-model.md
├── quickstart.md
├── contracts/
│   └── public-api.md
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
src/hunches/
├── __init__.py          # exports: -LocalCorpus -search -asearch  +Table +get_candidates +aget_candidates
├── search.py            # -LocalCorpus  +Table, table_rows(), readers per corpus kind (Table, Pg
│                        #   incl. two-table and server-side filter, S3 list_vectors),
│                        #   search_table() (one pass for all seeds); search_vectors loses its local branch
├── candidates.py        # Candidates.source + guards + repr branches + read/write meta;
│                        #   get_candidates/aget_candidates (seeds branch = the old asearch body)
└── evaluation.py        # band_sample: reject non-seed lists

tests/
├── test_table.py        # new: every input form, validation, vectors
├── test_candidates.py   # extended: source, guards, repr, round trip, ranking, limit, argument rules
├── test_search.py       # extended: S3 list_vectors stub; Table vectors in search_vectors
├── test_search_pg_keywords.py   # new: fake psycopg, reader + server-side statement, two-table
├── test_corpus.py, test_search_pg_*.py, test_e2e.py, test_pre006_fixtures.py,
│   test_public_api.py, test_pg_integration.py, test_skills.py, test_docs.py
│                        # updated for the renamed call and the removed corpus
└── fixtures/pre006/corpus → a single table file

examples/sample/         # corpus/ folder → corpus.jsonl; walkthrough.py and .ipynb together
README.md, docs/agent-instructions.md, AGENTS.md, skills/hunches/**, .kiro/steering/hunches.md,
pyproject.toml + plugin.json + .claude-plugin/*.json (descriptions), examples/sample/README.md
```

**Structure Decision**: the existing single-package layout. Corpus descriptors and all reading code
stay in `search.py`; candidate construction and the result type stay in `candidates.py`. No new
module, because the new code is a few functions beside the code it mirrors. The one candidate for a
new file, the Table reader, stays in `search.py` next to the other readers until it outgrows
them (shortcut: `search.py` is already about 700 lines; split only if a reviewer asks).

## Risks and how the plan handles them

- **Server-side SQL is untestable here** (no Postgres): tests assert the exact statement text and
  parameters with the fake; correctness on a real database is a listed human check.
- **S3 order is the service's**: documented in the contract; a `limit` there is not repeatable.
- **Ranking recount on server-side regexes can disagree with Postgres**: kept rows rank last with a
  single warning (contract).
- **The constitution called the library "already embedded"** (its first sentence). Amended by the
  user's approval to version 1.0.1 (wording-only PATCH, no principle touched). `AGENTS.md` and the
  other wording sites (research R9) are fixed in the documentation tasks.
- **Seed search over a `Table`** reads the table once for all seeds (`search_table`), not once per
  seed as the old local branch did (research R11).
- **Async**: blocking reads run in one `asyncio.to_thread` call (research R12).
- **Breaking rename**: all callers found by grep (research R9); `test_public_api.py` pins the new
  names; `test_docs.py` and `test_skills.py` fail on any doc block that still uses a removed name.
- **The "not run here" paths**: Parquet through pandas needs pyarrow, which is not installed in
  this environment; the polars path is exercised by tests, the pandas path by a skip-if-missing test.

## Complexity Tracking

No constitution violations to justify. Empty.

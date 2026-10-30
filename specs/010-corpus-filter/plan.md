# Implementation Plan: Filter the corpus before candidates are drawn

**Branch**: `claude/eager-ritchie-mvh7wf` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-corpus-filter/spec.md`

## Summary

Each corpus class gets one optional field, `where`, in its backend's own form:
- `Table`: a polars expression;
- `PgCorpus`: a SQL condition with its values written in;
- `S3Corpus`: the S3 Vectors filter document.

Every read of a filtered corpus sees only the items that pass: the whole corpus, keywords and
seeds. `Table` reading is rewritten onto polars only, which makes polars and pyarrow core
dependencies. `goldlabel-connect` teaches agents each form so they can help users write one.

Approach: the filter is applied at the corpus readers that already exist (`table_rows`,
`pg_items`, `search_pg_exact`, `_search_pg_index`, `search_vectors`, `s3_items`), so
`candidates.py` and `get_candidates` do not change. The new code is:
- one small helper that builds the Postgres fragment;
- one S3 filter checker and one matcher;
- deleting the `csv`/`json`/pandas reading in `Table`.

The facts behind each decision, checked against the installed versions, are in
[research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11+ (`requires-python = ">=3.11"` in `pyproject.toml`; AGENTS.md
still says 3.12, which is out of scope here).

**Primary Dependencies**: adds `polars` and `pyarrow` to the core dependencies (user decision,
2026-10-30; research R3). Everything else is already present: `psycopg.sql` (`pg` extra) and
`boto3` (`s3` extra). pandas stays optional, for `.to_pandas()` and pandas input only.

**Storage**: read-only, as before. No new file is written.

**Testing**: `pytest`, the fake `psycopg` (`tests/test_search_pg_*.py`), `FakeS3`
(`tests/test_search.py`), hand-written expected ids, and `tests/test_pg_integration.py` against a
real pgvector in CI only. Baseline: 621 passed, 18 skipped (`uv sync --all-extras`).

**Target Platform**: notebooks and scripts on any OS polars and pyarrow ship wheels for.

**Project Type**: library plus agent plugin (`src/goldlabel/skills/`).

**Performance Goals**: no new target.
- Table filtering runs in polars, natively and in parallel.
- Postgres filtering runs in the database, and only matching rows are sent.
- S3 listing still reads every vector, then drops non-matching ones; ListVectors has no filter.

**Constraints**:
- `import goldlabel` still imports neither polars nor pyarrow (`test_public_api.py`).
- Postgres stays read-only, with identifiers through `sql.Identifier`.
- The user's condition is passed through as `sql.SQL`, never parsed, inside one CTE,
  `goldlabel_where`, for both layouts (research R4).

**Scale/Scope**:
- `Table` is still read into memory, as today.
- Postgres whole-corpus reads stay bounded by `max_result_mb` while streaming. The up-front
  refusal is skipped when filtered (spec edge case).

## Constitution Check

*Gate: passed before research; re-checked after design (below).* The Ponytail skill was invoked
(`ponytail`) before the spec revisions and before drafting this plan, and its ladder was applied.
`/ponytail-review` was run on spec, plan and tasks before `/speckit-implement` (2026-10-30); findings 1-4 fixed (one Postgres fragment form, hand-written SQL expectations, honest red/regression wording in T001, empty S3 document refused).

| Principle | Check | Result |
|---|---|---|
| I. Gold rule | No path writes or suggests a gold label. The filter only narrows what `get_candidates` reads. | Pass |
| II. Ponytail | One field per class and a plain `if` per corpus kind, at the readers that exist. No filter class, registry, base class or option object. Reuses `pg_connect`, `text_source`, `pg_message`, the S3 loops, and the dataclass `repr`. Deletes more Table reading code than it adds. The skipped list is in the spec. | Pass |
| III. Spec Kit | `spec.md` decisions recorded by the user, `plan.md` here, `tasks.md` next. One commit per task, `010/TNN: ...`. No generated Spec Kit file is edited. | Pass |
| IV. Test-first | Each behaviour gets a failing test first, with hand-written expected ids. Fake `psycopg` and `FakeS3`, no real service. Real Postgres and S3 are human checks ([quickstart.md](quickstart.md) sections 3-4); `test_pg_integration.py` is CI-only. | Pass |
| V. No hidden state | The filter lives on the corpus object the caller built. Nothing is stored, no file is read, and no env var is added. | Pass |
| VI. Honest costs | Unchanged. A filter never costs money. | Pass |
| VII. Notebooks | No new I/O function, so the existing sync and async forms cover it. The `repr` shows the filter. `to_polars`/`to_pandas` are kept together. Import stays free of polars and pandas. | Pass |
| Constraints: Stack | Adds two core dependencies, justified in Complexity Tracking. The constitution's Stack line and `AGENTS.md` are updated in the same change (PATCH via `/speckit-constitution`). | Pass, with justification |
| Constraints: APIs | Checked against installed polars 2.1.0, psycopg 3.3.6 and the botocore `s3vectors` model, plus current docs (research R1-R5). | Pass |

**Post-design re-check**: unchanged. The design adds 3 fields, 3 private helpers (`_pg_where`, a CTE,
`_s3_check`, `_s3_match`) and no public name. Two existing behaviours change as a consequence of
the user's polars-only decision. Both are recorded below and in the spec.

## Behaviour changes (from the polars-only decision)

1. A list of rows or a JSONL file whose text column mixes strings and numbers is now read with
   the numbers as text. Polars does this even in strict mode, and it cannot be turned off.
   Previously that row was refused.
2. A vector column that mixes lists with strings or nested lists now fails with "Table: polars
   could not read the source: ...", which does not name the row. A `None` or a wrong-length
   vector still gets today's per-row message.
3. Parquet can no longer be read through pandas when polars is missing, since polars is now
   always installed.

## Existing tests that change

| Test | Change | Why |
|---|---|---|
| `test_table.py::test_validation_names_...` case `[{"text": "a"}, {"text": 5}]` | expects `"5"` to be read | behaviour change 1 |
| `test_table.py::test_a_bad_vector_fails_naming_its_row` | the `"abc"` and `[[1.0, 0.0]]` cases expect "polars could not read" | behaviour change 2 |
| `test_table.py::test_parquet_through_pandas_when_polars_is_missing`, `::test_parquet_with_neither_library_names_both` | deleted | behaviour change 3 |
| `importorskip("polars")` / `("pyarrow")` lines in `test_table.py` | removed | both are always installed |
| `test_notebook.py::test_missing_library_message` | the `polars` case is dropped (pandas stays) | `_frame.to_polars` loses its dead "not installed" branch (T001) |

Every other test passes unedited (spec SC-004).

## Project Structure

### Documentation (this feature)

```text
specs/010-corpus-filter/
├── spec.md
├── plan.md              # this file
├── research.md          # R1-R6, facts checked 2026-10-30
├── data-model.md        # the three `where` fields
├── quickstart.md        # automated and human checks
├── contracts/corpus-filter.md
├── checklists/requirements.md
└── tasks.md             # next: /speckit-tasks
```

### Source Code (repository root)

```text
pyproject.toml                       # polars + pyarrow core; polars out of the dev group
src/goldlabel/
├── search.py                        # Table.where + polars reader; PgCorpus.where + _pg_where; S3Corpus.where + _s3_check/_s3_match
├── _frame.py                        # drop the dead "polars is not installed" branch
└── skills/
    ├── goldlabel-connect/SKILL.md   # "Filter the corpus (optional)": a form, examples and pitfalls per corpus
    └── goldlabel-candidates/SKILL.md # one line: the filter belongs on the corpus
README.md                            # one filter example per corpus, the text-table rule
AGENTS.md                            # Stack line, Current state (010)
.specify/memory/constitution.md      # Stack line (PATCH, /speckit-constitution)
tests/
├── test_table.py                    # polars reader, Table.where, the edits above
├── test_search.py                   # S3: filter sent, listing matched, _s3_check refusals, undocumented rules
├── test_search_pg_keywords.py       # pg_items with where: 4 query shapes, %, params never None, text-table hint
├── test_search_pg_exact.py          # step 1 carries the fragment
├── test_search_pg_index.py          # index query carries the fragment
├── test_skills.py                   # exec the Table filter block
└── test_pg_integration.py           # real pgvector (CI): where in every mode, LIKE '%..%', doubled quote
```

**Structure Decision**: no new module. Everything sits beside the reader it changes in
`search.py`, as 007 did.

## Complexity Tracking

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `polars` as a core dependency | The user decided `Table` reads and filters with polars only, and the filter is a `pl.Expr`. | Keeping it optional would leave `Table`, the default corpus, unusable on a plain install. |
| `pyarrow` as a core dependency | `pl.from_pandas` requires it (research R1). The user chose core over an extra. | An extra would make pandas input fail on a default install. |
| `_s3_match` (an evaluator for the S3 filter language) | ListVectors has no filter, so whole-corpus and keyword reads of a filtered S3 corpus must apply the document themselves. The user accepted this. | A separate Python function for listing would mean two filters that can disagree. |

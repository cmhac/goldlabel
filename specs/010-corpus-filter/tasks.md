---

description: "Task list for 010, corpus filters"
---

# Tasks: Filter the corpus before candidates are drawn

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/corpus-filter.md](contracts/corpus-filter.md), [quickstart.md](quickstart.md)

**Tests**: required. Constitution IV: red first, then green, with both runs shown and every
expected value written by hand. Use no real service; the fake `psycopg` and `FakeS3` already exist.

**Commits**: one per task, `010/TNN: ...`, on `claude/eager-ritchie-mvh7wf`. Before each commit run
`uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest`.

US4 (seed search over a filtered corpus) has no task of its own. Its scenarios are part of T002,
T003 and T004, because each backend's seed reader changes in the same place as its other readers.

## Phase 1: Foundational (blocks the Table filter)

- [X] T001 [US6] Make polars and pyarrow core dependencies and read every `Table` source with
  polars only (spec FR-003, FR-005; research R1, R3; plan "Behaviour changes" and "Existing tests
  that change").
  - Red first, in `tests/test_table.py`: a pandas object column `["a", 5]` raises `ValueError`
    matching "polars could not read" (fails today, with "non-empty").
  - Regression tests, which pass before and after and guard the polars traps in research R1:
    - a list of 150 rows where key `k` first appears in row 150 keeps `k`;
    - a CSV id `007` stays `"007"`;
    - a JSONL with a blank line and a row without the id column gives "row 1 ... key".
  - Then edit the tests the plan lists:
    - the `{"text": 5}` case now expects `[{"id": "0", "text": "a"}, {"id": "1", "text": "5"}]`;
    - the `"abc"` and `[[1.0, 0.0]]` bad-vector cases expect "polars could not read";
    - delete the two pandas-fallback Parquet tests;
    - drop the `importorskip("polars")`/`("pyarrow")` lines.
  - Implementation:
    - `pyproject.toml`: `polars` and `pyarrow` go in `dependencies`, `polars` comes out of the dev
      group, `pandas` stays there. Run `uv lock`.
    - `src/goldlabel/search.py`: replace `_parquet_rows` and the `csv`/`json`/`to_dicts`/`to_dict`
      branches of `table_rows` with one polars frame per source:

      | Source | Call |
      |---|---|
      | `.csv` | `pl.read_csv(path, infer_schema=False)` |
      | `.jsonl` | `pl.read_ndjson(path, infer_schema_length=None)` |
      | `.parquet` | `pl.read_parquet(path)` |
      | polars DataFrame | as it is |
      | pandas DataFrame | `pl.from_pandas(src)`, detected by `type(src).__module__.startswith("pandas")` |
      | anything else | `pl.DataFrame(list(src), infer_schema_length=None)` |

      - Re-raise a polars build error (and the pandas `TypeError`) as
        `ValueError(f"Table: polars could not read the source: {e}")`.
      - Check that the text and id columns are in `df.columns`, keeping today's "no column
        {column!r}" message, then run the existing per-row loop over `df.to_dicts()`.
      - An empty source still returns `[]`.
      - Import polars inside the function, never at module level.
      - Remove the now-unused `csv` and `json` imports, if nothing else in the file uses them.
    - `src/goldlabel/_frame.py`: delete the "polars is not installed" `ImportError` branch.
  - `tests/test_public_api.py` must still show that `import goldlabel` does not import polars.

## Phase 2: User Story 2 — the Table filter (P1)

**Independent test**: one tiny dataset as a CSV, JSONL, Parquet, polars, pandas and list source,
filtered by the same expression, gives the same hand-written ids.

- [X] T002 [US2] Add `Table.where` (spec Table form, FR-001, FR-002, FR-004, FR-008, FR-009; data
  model row "Table").
  - Red first, in `tests/test_table.py`:
    - rows `1,2,3` politics and `4,5` sports, with `pl.col("section") == "politics"`: `table_rows`
      gives ids `["1", "2", "3"]` for every source type;
    - `get_candidates(..., keywords=["ballot"])`, with ballot in rows 2 and 4, gives `["2"]`;
    - seeds over a vector table whose best match (row 4) is outside the filter: the best candidate
      is the best inside it, with hand-computed similarities as in `test_two_seeds_one_pass_...`;
    - a row filtered out with an empty text does not fail the read;
    - on a CSV, `pl.col("year").cast(pl.Int64) >= 2024` keeps the 2024 and later rows;
    - `Table(rows, where="section = 'x'")` and `where=lambda r: True` raise `TypeError` matching
      `pl.col`;
    - `where=pl.col("nope") == 1` raises `ValueError` matching `Table where:.*nope` on reading;
    - a non-boolean expression (`pl.col("text")`) raises `ValueError` matching `Table where:`;
    - `"section"` appears in `repr(corpus)`;
    - a row whose `section` is null is dropped.
  - Implementation in `src/goldlabel/search.py`:
    - field `where: Any = None` on `Table`;
    - in `__post_init__`, when `where` is not `None`, import polars and require
      `isinstance(where, pl.Expr)`;
    - in `table_rows`, `df = df.filter(table.where)` before the column checks, re-raising polars
      errors as `ValueError(f"Table where: {e}")`;
    - update the `Table` docstring with one line on `where` and one on CSV values being text.

## Phase 3: User Story 1 — the Postgres filter (P1)

**Independent test**: with the fake `psycopg`, a filtered corpus in every mode sends the condition
exactly once, and only filtered rows come back.

- [ ] T003 [US1] Add `PgCorpus.where` (spec PgCorpus form, FR-006, FR-008; research R4; data model
  fragment).
  - Red first, with hand-written SQL expectations:
    - `tests/test_search_pg_keywords.py`:
      - `pg_items` with `where="section = 'politics'"` covers the four shapes: single and two
        tables, with and without `match`.
      - Hand-write the expected fragment from the design; never copy it from the code's output
        (constitution IV). Single table (`posts`, id `id`): the SQL contains
        `"id" IN (SELECT "id" FROM "posts" WHERE (section = 'politics'))`. Two tables (`texts`):
        `t."id" IN (SELECT "id" FROM "texts" WHERE (section = 'politics'))`. Existing tests stay
        unchanged.
      - `params` is never `None` when `where` is set.
      - `where="body LIKE 'vote%'"` reaches the SQL as `LIKE 'vote%%'`.
      - Whole-corpus reads with `where` skip the planner-statistics refusal (no `table_estimates`
        query is sent) but keep the streaming check.
      - A two-table error whose message says a column does not exist gets "Filter columns must
        be in the text table".
    - `tests/test_search_pg_exact.py`: step 1 carries the fragment with `t."id"`. A condition on a
      column named `i` is inside the sub-query, never next to step 1's own `i`.
    - `tests/test_search_pg_index.py`: the index query carries the fragment.
    - In any of those files: `PgCorpus("t", where="")`, `where="  "` and `where=5` raise
      `ValueError`, and without `where` every existing SQL expectation is unchanged.
  - Implementation in `src/goldlabel/search.py`:
    - field `where: str | None = None` on `PgCorpus`, validated in `__post_init__`;
    - `_pg_where(corpus, id_expr)` returns the one fragment
      `{id_expr} IN (SELECT {key} FROM {source} WHERE ({cond}))`. `{source}` and `{key}` come
      from `text_source(corpus)`, and `{cond}` is `sql.SQL(corpus.where.replace("%", "%%"))`;
    - add it to the four `pg_items` queries, to step 1 of `search_pg_exact` and to
      `_search_pg_index`;
    - pass `()` instead of `None` as the parameters when `where` is set;
    - skip the up-front estimate in `pg_items` when `where` is set;
    - in `pg_message`, add the text-table line when `corpus.where and corpus.text_table` and the
      message contains "does not exist".
  - `tests/test_pg_integration.py` (runs only with `GOLDLABEL_TEST_PG_URL`): `where` in whole
    corpus, server-side keywords and exact seeds, a `LIKE '%..%'` condition, and a doubled quote,
    on the single and two-table fixtures.

## Phase 4: User Story 3 — the S3 Vectors filter (P2)

**Independent test**: with `FakeS3`, seeds send the document unchanged, and listing keeps exactly
the hand-picked keys.

- [ ] T004 [US3] Add `S3Corpus.where` (spec S3 form, FR-007, FR-008; research R5).
  - Red first, in `tests/test_search.py`:
    - `search_vectors` sends `filter=` equal to the document, and no `filter` key without one;
    - `s3_items` on a listing of six vectors (`section`, `year`, `tags`, one missing `year`) keeps
      the hand-written keys for each of:
      - a bare value;
      - `$eq` against a list;
      - `$ne`, `$gt`, `$gte`, `$lt`, `$lte`;
      - `$in` and `$nin`, against scalars and lists;
      - `$exists` true and false;
      - `$and`, `$or`, and two keys at the top level;
      - each of the four undocumented rules in research R5;
    - `$startsWith` in a listing raises `ValueError` naming it;
    - `S3Corpus("b", "i", where=...)` refuses a non-dict, an empty dict, an unknown `$op`, an
      empty `$and`, an empty `$in`, `$gt` with a string and `$exists` with a string, each naming
      the path;
    - `get_candidates(corpus, keywords=[...])` over a filtered listing ranks only kept items.
  - Implementation in `src/goldlabel/search.py`:
    - field `where: dict | None = None` on `S3Corpus`;
    - `_s3_check(where, path="where")`, called from `__post_init__`;
    - `_s3_match(where, metadata)`;
    - `params["filter"] = corpus.where` in `search_vectors` when set;
    - the match check in the `s3_items` loop.
  - Add a `shortcut:` comment on `_s3_match` noting that the undocumented rules are unverified
    against the service (quickstart section 4).

## Phase 5: User Story 5 — agents help write filters (P2)

- [ ] T005 [US5] Teach the filters (spec "Agent skills", FR-010, FR-011, User Story 5; research
  R6).
  - Red first, in `tests/test_skills.py`:
    - `goldlabel-connect/SKILL.md` has a "Filter the corpus" section with a code block per corpus
      type, naming `where=` for `gl.Table`, `gl.PgCorpus` and `gl.S3Corpus`;
    - the Table block runs with `exec` against a tiny fixture and keeps the expected ids, as
      `test_connect_skill_shaping_example_runs_and_leaves_the_source_alone` does;
    - the section mentions "text table" and that CSV values are text.

    In `tests/test_docs.py`: the README has a filter example per corpus type.
  - Then write:
    - `src/goldlabel/skills/goldlabel-connect/SKILL.md`: the form, and examples for one value,
      several values and a range, per corpus type. Add the pitfalls from the spec and the agent
      steps:
      1. look up the real names and values (the Table's schema and a few rows; for Postgres,
         columns the user or a schema query of theirs shows; a few listed S3 vectors' metadata);
      2. show the filter and explain it in plain words;
      3. wait for the user's yes;
      4. suggest `gl.get_candidates(corpus, limit=20, out=False)` to check it.

      The agent never chooses a filter, column or value itself.
    - `src/goldlabel/skills/goldlabel-candidates/SKILL.md`: one line saying the filter belongs on
      the corpus (`where=`), not on `get_candidates`.
    - `README.md`: one short "Filter the corpus" block covering all three forms, the text-table
      rule, and that polars and pyarrow are now installed with goldlabel. Fix line 23's
      `pip install polars`.

## Phase 6: Polish

- [ ] T006 Records and the final check.
  - `AGENTS.md`: the Stack line (core: polars, pyarrow; dev group: pandas only for the export
    tests) and "Current state" (010 implemented, plus what a human still has to do: quickstart
    sections 3-5).
  - `.specify/memory/constitution.md`: the Stack line, through `/speckit-constitution` as a
    PATCH (1.2.1), recording that the user approved the dependencies on 2026-10-30.
  - Run `quickstart.md` section 1 and report the output.
  - Run `/ponytail-review` on the diff and `/ponytail-debt`, fix what the review finds, and
    report both.

## Dependencies

T001 -> T002. T003 and T004 depend on nothing and touch separate functions in `search.py`, so they
are kept sequential to avoid conflicts. T005 after T002-T004, because its examples use the real
API. T006 last.

## Implementation strategy

T001 + T002 are the Table MVP, and T003 is the Postgres case that prompted the request. Each task
leaves every check green, so the branch can stop after any task.

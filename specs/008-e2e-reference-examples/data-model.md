# Data Model: End-to-end reference examples

All files live in `e2e/common/` unless stated. Nothing here is a library type; these are the files
the examples read and the shapes the offline test checks.

## corpus.jsonl

One JSON object per line, 60 lines, ids unique.

| Field | Type | Rule |
|---|---|---|
| `id` | string | unique, stable; the text is never edited after labelling |
| `text` | string | non-empty; at least one item each with `%`, `_` and `\` |
| `embedding` | list of 2 floats | unit length; both numbers from the Pythagorean table in research R3 |

The same data is loaded into every backend: written as CSV (text only), Parquet, JSONL, polars,
pandas and rows by the table example; as `id`/`text`/`embedding` rows by the Postgres, pgvector
and S3 examples (two-table layout: `posts(id, ...)` and `texts(id, text)`).

## taxonomy.yaml, prompt.md

`mode: single`, `labels: {layoff: ..., burnout: ...}` (the built-in `off_topic` is added by the
library). `prompt.md` is the classifier prompt text. Both are inputs to the cache key, so changing
either invalidates cached model results and makes gold rows stale until re-checked.

## seeds.json

`{"<seed phrase>": [x, y]}`. The stand-in embedder returns the vector for the phrase and raises on
an unknown one. Seeds are axis-aligned (1,0) and (0,1) so cosine similarity equals a coordinate.

## expected.json

Hand-written. Keys are filter names used by the examples; values are what the library must return.

| Section | Content |
|---|---|
| `whole` | every id, in corpus order |
| `keywords.<name>` | ordered ids with `terms_matched` and `matches` for each hit (plain terms, a regex with an inline flag, `%`, `_`, backslash), and the same ordered list under `limit` |
| `seeds` | per seed: ids with similarity and band, and each item's `best_seed`, at the floor the examples use |
| `score_floor` | the lowest evaluation score an example accepts (a lower bound; model output is not pinned) |

Every id here must exist in the corpus; the offline test checks it.

## gold.jsonl and GOLD.md

`gold.jsonl` is exactly the file the labelling page wrote: `GoldRow` lines (`id`, `text`, `labels`,
`split`, `labelled_by`, `labelled_at`). About 40 rows, 30 `dev` and 10 `test`. No agent or script
edits it. `GOLD.md` records who labelled, when, and the commit of the corpus, taxonomy and prompt
they labelled against. Offline checks: every row's id and text equal a corpus item; every label is a
taxonomy label; `labelled_by` is `hunches-ui`.

## Throwaway service (runtime, not a file)

| Attribute | Value |
|---|---|
| name | `hunches-e2e-<example>-<pid>` |
| label | `hunches-e2e=<example>` (used to sweep stale containers) |
| image | pinned tag recorded in the example's README |
| host port | random free port on `127.0.0.1`, read back with `podman port` |
| lifetime | one run; removed in `finally`, `atexit` and on SIGTERM |

## Result cache and working folder (runtime)

- `e2e/.cache/`: the classifier's cache directory, passed as `cache=` everywhere; git-ignored; also
  holds the library's `cost.json`.
- A per-run `tempfile.TemporaryDirectory()`: the gold copy, candidates files, evaluation log
  (`hn.settings.root` points here), generated CSV/Parquet. Removed at the end.

## Result line

`RESULT: pass|fail|skipped - <text>`, last line of an example's output. See
[contracts/example-run.md](contracts/example-run.md).

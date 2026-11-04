# Data model: 014

No file format changes for gold rows. One new key on one log event.

## Gold dataset (`Gold`)

| Attribute | Type | Rule |
|---|---|---|
| `candidates` | `Candidates \| None` | needed only to draw |
| `name` | `str \| None` | `[A-Za-z0-9_-]+`; `None` is the default dataset |
| `path` | `Path` | `path` argument, else `<root>/gold.jsonl` (no name) or `<root>/gold-<name>.jsonl` |
| `sample_size` | `int` | `>= 1`, default 50; the default `n` of each split |

Companion files are derived from `path` exactly as today: `<path>.lock`, `<path>.tmp`, `<stem>.removed.jsonl`.

Draw order key (not stored): `sha256(f"{name or ''}\0{id}")`.

## Sample

A live view; stores no rows.

| Attribute | Type | Meaning |
|---|---|---|
| `gold` | `Gold` | the dataset it reads |
| `split` | `"dev" \| "test"` | its split |
| `drawn` | `int` | rows the call that returned it added (0 for `gold.dev` / `gold.test` and for a rerun) |
| `rows` | `list[GoldRow]` (property) | that split's rows in the file now, labelled and pending |
| `path`, `name` | `Path`, `str` | `gold.path`, `split` (what `_aevaluate` reads) |

Summary: `Sample dev of corpus-b (.goldlabel/gold-corpus-b.jsonl): 50 rows (20 labelled, 30 pending); drew 30 now`, or `...; nothing drawn` / `...; already has 80, asked for 30`.

## Gold row (`GoldRow`)

Unchanged: `id`, `text`, `labels`, `split`, `labelled_by`, `labelled_at`, `note`, extra keys kept.

## Labelling pass (in memory, `Handle`)

`split` and `ids` (the pass), fixed when `serve` starts. `/api/state` gains `"split"`.

## Evaluation log (`evals.jsonl`)

Evaluation lines: unchanged (already carry `"gold"`). `test_folded` events gain `"gold": "<path>"`. Events without it are read as belonging to a file named `gold.jsonl`.

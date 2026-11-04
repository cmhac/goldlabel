# Data model: 014

## Gold dataset (`Gold`)

| Attribute | Type | Rule |
|---|---|---|
| `candidates` | `Candidates \| None` | needed only when a draw has a shortfall |
| `name` | `str \| None` | `[A-Za-z0-9_-]+`; `None` is the default dataset |
| `path` | `Path` | `<root>/gold.jsonl` or `<root>/gold-<name>.jsonl`, fixed at creation |
| `sample_size` | `int` | `>= 1`, default 50 |

Companions, derived from `path` as today: `<path>.lock`, `<path>.tmp`, `<stem>.removed.jsonl`. Log: `path.parent / "evals.jsonl"`.

Draw order key (not stored): `sha256(f"{name or ''}\0{id}")`.

## Gold row (`GoldRow`)

As today (`id`, `text`, `labels`, `split`, `labelled_by`, `labelled_at`, `note`, extra keys kept), plus:

| Field | Type | Rule |
|---|---|---|
| `sample` | `str \| None` | written by draws and `import_rows`; omitted from the file when `None`; a row's sample is `sample or split` |

All rows with one sample name share one split.

## Sample

A live, read-only view; stores no rows.

| Attribute | Type | Meaning |
|---|---|---|
| `gold` | `Gold` | the dataset |
| `names` | `tuple[str, ...]` | one sample, or the samples of a combination |
| `split` | `"dev" \| "test" \| None` | `None` for a combination |
| `drawn` | `int` | rows the call that returned it added (0 for `gold[name]`, a rerun, or `+`) |
| `rows` | `list[GoldRow]` (property) | rows of those samples in the file now |
| `path` | `Path` | `gold.path` |

Summary examples:

- `Sample "dev" (dev) of default: 50 rows (20 labelled, 30 pending); drew 30 now`
- `Sample "test" (test) of corpus-b: 30 rows (30 labelled, 0 pending); nothing drawn; evaluated, spent`
- `Sample "dev" + "test" of default: 100 rows (100 labelled, 0 pending)`

## Labelling pass (in memory, `Handle`)

`sample` and `ids`, fixed when `serve` starts. `/api/state` gains `"sample"` and `"split"`.

## Evaluation log (`evals.jsonl`)

Evaluation lines gain `"samples": [names]` and `"rows_digest"`. Old lines without them count for the sample named after their `split` and are never "identical" to a new one. Old `test_folded` events are ignored.

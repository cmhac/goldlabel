# Data model: 014

## Gold dataset (`Gold`)

| Attribute | Type | Rule |
|---|---|---|
| `candidates` | `Candidates \| None` | needed only when a draw has a shortfall |
| `name` | `str \| None` | `[A-Za-z0-9_-]+`; `None` is the default dataset |
| `path` | `Path` | `<root>/gold.jsonl` or `<root>/gold-<name>.jsonl`, fixed at creation |
| `sample_size` | `int` | `>= 1`, default 50 |

These companion files are derived from `path`, as today:

- `<path>.lock`
- `<path>.tmp`
- `<stem>.removed.jsonl`

The evaluation log is `path.parent / "evals.jsonl"`.

The draw order key is `sha256(f"{name or ''}\0{id}")`. It is not stored.

## Gold row (`GoldRow`)

The fields are as today: `id`, `text`, `labels`, `split`, `labelled_by`, `labelled_at` and `note`, and extra keys are kept. One field changes:

| Field | Was | Now |
|---|---|---|
| `split` | `"dev" \| "test"` | the sample name, any `[A-Za-z0-9_-]+` |

Old files are valid unchanged.

## Sample

A Sample is a live, read-only view. It stores no rows.

| Attribute | Type | Meaning |
|---|---|---|
| `gold` | `Gold` | the dataset |
| `names` | `tuple[str, ...]` | one sample, or the samples of a combination |
| `drawn` | `int` | rows added by the call that returned it; 0 for `gold[name]`, a rerun, or `+` |
| `rows` | `list[GoldRow]` (property) | the rows of those samples in the file now |
| `path` | `Path` | `gold.path` |

Summary examples:

- `Sample "dev" of default: 50 rows (20 labelled, 30 pending); drew 30 now; not evaluated`
- `Sample "test" of corpus-b: 30 rows (30 labelled, 0 pending); nothing drawn; evaluated 2 times (2 prompts)`
- `Sample "dev" + "test" of default: 100 rows (100 labelled, 0 pending); evaluated 1 time (1 prompt)`

## Labelling pass (in memory, `Handle`)

The pass is `sample` and `ids`, fixed when `serve` starts. `/api/state` gains `"sample"`.

## Evaluation log (`evals.jsonl`)

Evaluation lines gain two keys:

- `"samples"`: the list of names;
- `"rows_digest"`.

`"split"` becomes `" + ".join(names)`.

Older lines without `"samples"` count for the sample named in their `split`, and are never "identical" to a new line. Old `test_folded` events are ignored.

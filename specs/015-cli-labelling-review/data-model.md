# Data model: 015

## Gold file (`gold.json`, `gold-<name>.json`)

```json
{
  "taxonomy": {"mode": "single", "labels": [{"name": "yes", "description": "…"}]},
  "rows": [
    {"id": "a17", "text": "…", "labels": ["yes"], "sample": "dev",
     "labelled_by": "goldlabel-ui", "labelled_at": "2026-11-05T10:00:00+00:00", "note": "…",
     "revisions": [{"at": "2026-11-06T09:00:00+00:00", "labels": ["no"], "note": null, "labelled_by": "imported"}]}
  ]
}
```

- `taxonomy` is `null` until `gl.label` stores one. Replaced whole by `gl.label` when it differs; never touched by anything else.
- A row keeps every 014 field. `revisions` is omitted when empty. Entries are oldest first; each holds the values the row had just before that change. `labelled_by` and `labelled_at`/`labels`/`note` at the top level are the current values.
- A first label (row had no labels) adds no entry. A save that changes neither labels nor note changes nothing.
- File name: `gold.json` (default dataset) or `gold-<name>.json`, `<name>` matching `[a-z0-9_-]+`. `gold*.removed.jsonl` keeps its line-per-row form. 014-format files are not read.

## `evals.jsonl` line (additions only)

`"disagreements": [{"id": "a17", "gold": ["yes"], "predicted": ["no"], "reasoning": "…"}]`, `predicted` is `null` for an item that failed. Older lines have no key. `_history` and the identical-rerun test are unchanged.

## Lock (`labelling.lock`, in the storage folder)

`{"pid": 123, "port": 51234, "started": "2026-11-05T10:00:00+00:00"}`. Created readable by the default umask (no secret in it). Removed when the server stops.

## Pass (in memory, in the server)

`id`, `dataset`, `sample names`, `ids` (fixed at start), `review` (force), `current`, `history`, `ended`. Methods are the 013 `Handle` methods (state, label, back, skip) plus `pending()` and `end()`.

## Derived, never stored

- **Dataset list**: one entry per matching file: name, `taxonomy` present or not, samples with rows, labelled, pending; or `error` with the message.
- **Evaluation view**: each log line whose `samples` include the sample: time, samples, score, target, PASS/FAIL, n, skipped, model, prompt digest, `stale`, `stale_rows` (ids revised after it), and its disagreements joined with the row's text, current labels, note, `revised` (a revision after the line's time) or `missing`.

# Interfaces: 015

## Command

```text
goldlabel label [NAME] [--dir PATH] [--port N]
```

- Folder: `--dir`, else `GOLDLABEL_DIR`, else `.goldlabel/`.
- With a live server for the folder: print its URL (`…/#/d/gold-NAME` when `NAME` is given), open the browser, exit 0.
- Otherwise: bind 127.0.0.1 (`--port`, default a free one), write the lock, print `Labelling page: <url>`, the folder and the gold rule's short line, open the browser, run until Ctrl-C, then remove the lock.
- Exit 1, nothing started: no `gold*.json` in the folder; `NAME` given and `gold-NAME.json` (or `gold.json` for the default) missing (the datasets that exist are printed); the port is in use; the lock is stale and cannot be replaced.
- There is no flag that sets, imports or edits a label, or takes a taxonomy.

## Python

- `gl.label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None) -> Sample`.
  - No live server: its own server writes `taxonomy` into the sample's gold file when it differs.
  - Live server for the folder: `POST /api/pass` (with the taxonomy; the server writes it, this process writes no gold file), print `Labelling page: http://127.0.0.1:PORT/#/pass/<id>`, wait until `pending == 0` or `ended` (not at all with `force_open_ui=True`), return the `Sample`.
  - No live server: start one in this process that stops on **Done**, as in 012-014.
  - `port` applies only when it starts a server.
- `Gold`: file names end in `.json`; `GoldRow.revisions`; no new public name. Nothing else in `__all__` changes.
- `clf.evaluate`/`aevaluate`: the `evals.jsonl` line also carries `disagreements`.

## HTTP (127.0.0.1 only)

Every request must have `Host: 127.0.0.1:<port>` or `localhost:<port>`, else 403. Every non-GET must have `X-Goldlabel: 1`, else 403. Bodies are JSON objects up to 1 MB, else 400. Errors are `{"error": text}`.

| Route | Reply |
|---|---|
| `GET /`, `/app.js`, `/app.css` | the page files (no token) |
| `GET /api/datasets` | `[{name (file stem: gold, gold-<name>), title (default or <name>), taxonomy: bool, samples: [{name, rows, labelled, pending}], error?}]` |
| `GET /api/rows?dataset=&sample=` | `[{id, labels, note: bool, revised: bool}]` |
| `GET /api/row?dataset=&id=` | `{id, text, sample, labels, note, labelled_by, revisions, options: [{name, description}], mode, stored_taxonomy: bool}`; 404 unknown id |
| `POST /api/label` `{dataset, id, labels, note?, pass?}` | validates, writes (first label, revision, or no-op); with `pass` it advances that pass and returns its state, else returns the row as `/api/row` |
| `GET /api/evals?dataset=&sample=` | the evaluation view (data-model.md), newest first |
| `POST /api/pass` `{dataset (stem), samples: [str], force?: bool, taxonomy?: object}` | `{pass: ID}` (random string); stores the taxonomy when given; 400 if it does not validate |
| `GET /api/pass/ID` | the 013 state object plus `pending` and `ended` |
| `POST /api/pass/ID/back`, `/skip` | the state |
| `POST /api/pass/ID/done` | the state; marks the pass ended; stops the server only if it was started by `gl.label` |

No route runs an evaluation or a model, and none returns a prediction as a label suggestion.

## Page routes (`location.hash`)

`#/` datasets · `#/d/<dataset>` samples · `#/d/<dataset>/s/<sample>` rows and evaluations · `#/d/<dataset>/r/<id>` revise one row (**Jump to id** is a text field on dataset and sample pages) · `#/pass/<id>` the labelling pass (an unknown id shows "this pass has ended"). `<dataset>` is the file stem (`gold`, `gold-corpus-b`); the page shows `default` for `gold`.

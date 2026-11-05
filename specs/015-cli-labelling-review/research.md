# Research: 015 CLI labelling page

Every open question was settled in the spec's Clarifications. These are the design choices the plan adds, each checked against the code in `src/goldlabel/_label.py`, `gold.py`, `evaluation.py`, `cli.py` and `web/app.js`.

## Decisions

**1. Gold file shape.** `{"taxonomy": null | {mode, labels:[{name, description}]}, "rows": [GoldRow.dump()…]}`, written atomically as now (`tmp` then `os.replace`). Name: `gold.json` and `gold-<name>.json`. Rationale: the user's decision; one place for the taxonomy; `GoldRow` already allows extra keys (`extra="allow"`). Alternatives: a sidecar file (the user rejected it), a header line in the JSONL (still a format break, less readable).

**2. `_write(rows, taxonomy=KEEP)`.** The function that rewrites the file rereads the document to keep the stored taxonomy unless one is passed. `draw_sample`, `import_rows`, `remove` and the page's saves therefore keep it without knowing it exists. Only `gl.label` passes a taxonomy. Alternative: store it on `Gold` in memory: rejected, because a `Gold` object may be older than the file.

**3. `revisions` on the row.** A plain `list[dict]` field, `None` by default and dropped on dump when empty, like the other optional keys. An entry is `{"at", "labels", "note", "labelled_by"}` holding the values just before the change. No class. Alternative: a `Revision` model: rejected, nothing validates it.

**4. Staleness.** `any(entry.at > line.time for row in sample rows for entry in row.revisions)`, comparing parsed datetimes (both are `datetime.now(UTC).isoformat()`). A combination line is stale if any named sample is. Alternative: the rows digest the log already stores: rejected by the user.

**5. Disagreements in the log.** `{"id", "gold", "predicted", "reasoning"}` added to the line `_aevaluate` writes, taken from `Evaluation.disagreements` without the text. The identical-rerun rule is unchanged (`same` does not include it). Text, current labels and note are joined from the gold file at view time; a missing id is reported as removed. Alternative: recompute from the classifier cache: rejected, needs the classifier and prompt in the page.

**6. Datasets.** The server lists `gold.json` and `gold-<name>.json` in its folder with `re.fullmatch(r"gold(-[a-z0-9_-]+)?\.json")`, and builds a `Gold` per request with `Gold(name=…)` whose `.path` is then set inside the server's folder (a `Gold` resolves its path from `settings.root`, which a notebook may change after the server started). One comment marks that line.

**7. Lock.** `labelling.lock` in the folder: `{"pid", "port", "started"}`, created with `O_EXCL` after the socket is bound (the port is known only then). A server is live when the pid is alive and `GET /api/datasets` on that port answers 200. A dead pid, a closed port or unreadable JSON replaces the lock. The 012-014 per-gold-file `.lock` and the "already being labelled" error are deleted along with their tests.

**8. Passes.** `Server.passes: dict[int, Pass]`, ids counted up from 1. `POST /api/pass {dataset, samples, force}` creates one over the rows pending now (every row with `force`) and returns its id; the other pass routes carry that id. A `Pass` records `ended` when **Done** is posted. `GET /api/pass/<id>` returns `{pending, ended}` for the joined `gl.label` to poll once a second. Rationale: reuses the 013 logic untouched. Alternative: client-side passes: rejected, the server must stay the one to decide the next row.

**9. Who stops the server.** A `Server` started by `gl.label` stops on **Done** (as today). One started by the command never does, and **Done** only marks the pass ended and returns the page to `#/`. A flag `stop_on_done` on the server.

**10. Join from `gl.label`.** `label()` writes the taxonomy, then: if the lock is live, `POST /api/pass`, print the URL, poll `GET /api/pass/<id>` (`time.sleep(1)`) until `pending == 0` or `ended`, return the `Sample`; an interrupt just propagates. With `force_open_ui=True` it prints and returns at once. If no live lock, it starts a `Server` in-process as today. The command with a live lock prints that server's URL and exits 0.

**11. Local access.** No token. The Host check stays (`127.0.0.1:<port>` or `localhost:<port>`). Every non-GET request must carry `X-Goldlabel: 1`, which the page's `fetch` sets; a cross-site page cannot send it without a permission check the server never answers. Sources: MDN CORS (preflight for non-simple requests) and the CSRF write-ups it links.

**12. Page routing.** `location.hash` routes; each render reads the hash and fetches its data. The browser's Back, forward and reload work with no code. The rows list's `scrollY` is saved per hash in a `Map` before navigating and restored after render. Alternative: server-held history (today's `_history`): kept only inside a `Pass` for Back during labelling.

**13. Layout.** From `lg` (1024px), each card gets `lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto`, the text card is `lg:sticky lg:top-4` like the controls card, both `tabindex="0"` with the existing focus classes. Below `lg` nothing changes. `app.css` is rebuilt with Tailwind v4.3.3 (the pinned binary downloads from GitHub releases; checked reachable from this environment).

**14. Taxonomy when there is none stored.** Labels already used in the dataset's rows, mode `multi` if any row has more than one label, else `single`, no descriptions; the page says so. Revisions and labels validate with the same `validate_labels`.

## Skipped (Ponytail)

A router library, a state store, a table component, pagination of the rows list, a lock library, polling the page for changes, a second log, a model for revisions, server-sent events for the waiting call.

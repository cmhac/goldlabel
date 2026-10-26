# 13 — Labelling server (no page yet)

Spec: "The labelling web page" (security, behaviour), FR-14, FR-16, FR-17, FR-19. **Verify the `http.server` classes against the installed Python's documentation first.**

**Do** in `src/hunches/_label.py`:
- A `ThreadingHTTPServer` bound to `127.0.0.1` (port `0` = random unless given). All state decisions are made **server-side** so the page's JavaScript stays thin and the logic is testable without a browser: the server decides which item is next.
- Per-run random token (`secrets.token_urlsafe`) required on every request (query or header); wrong or missing → 403. Reject requests whose `Host` header is not `127.0.0.1:<port>` or `localhost:<port>` (DNS-rebinding guard). No CORS headers, no cookies, no external requests.
- JSON API (all under `/api/`): `GET state` → current item (`id`, `text`), its position, progress (`done`, `total`), `labels` (name + description), `mode`, per-label counts, and whether the split is finished; `POST label` `{id, labels}` → validated with `taxonomy.validate_labels` (single: exactly one; multi: any; `off_topic` exclusive), written to the gold file immediately and atomically, stamped `labelled_by: "hunches-ui"`, `labelled_at`; `POST back` → previous item (its label can be changed by posting again); `POST skip`; `POST done` → stops the server and releases the lock. **The API never returns the classifier's prediction** and the server never calls a model.
- Lock: `<gold>.lock` containing the pid and a start time; a second server on the same file is refused with a clear error; a lock whose pid is not alive is replaced. Released on `done`, on `stop()` and at exit.
- `serve(gold, taxonomy, *, split=None, port=None) -> handle` with `.url`, `.wait()`, `.stop()`. It labels the first unlabelled row of the chosen split(s) and resumes there on a later start. Rows are shown in file order.
- Static files (`/`, `/app.js`, `/app.css`) are served from `src/hunches/web/` once task 14 adds them; here serve a one-line placeholder at `/`.

**Tests (red first, stdlib `http.client` against an ephemeral port, no browser)**: binds only to loopback; 403 without or with a wrong token; 403 for a foreign `Host`; `state` shows the first pending row and counts; labelling a `single` row with two labels or none is a 400 with the validation message; `multi` accepts several; `off_topic` with another label is a 400; after `label` the gold file on disk has the row labelled and stamped, and the other rows byte-identical; closing the server mid-way and starting another resumes at the next unlabelled row (nothing lost); `back` then relabel changes the stored label; `skip` leaves the row pending and moves on; `done` stops the server and removes the lock; second server refused; stale lock (dead pid) replaced; no response body anywhere contains a prediction field; the port is not reachable on a non-loopback address (assert the bound address).

**Not in this task**: HTML, CSS, JS, `hn.label`, the gold-rule text.

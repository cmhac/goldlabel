# Postgres without embeddings

Reference for a corpus in a plain Postgres table: no pgvector, no vectors needed.

## What it shows

- `hn.PgCorpus(table="corpus")` (id and text in one table) and
  `hn.PgCorpus(table="items", text_table="texts")` (text in a second table, joined on the id).
- The whole corpus and keyword and regular-expression search, each with `server_side=False` (read
  every row, match in Python) and `server_side=True` (the database filters first). The terms `%`,
  `_` and a backslash are escaped for `LIKE`, so they match only themselves. Both give the same hits
  in the same order as the table example.
- The result size limit: `PgCorpus(table="big", max_result_mb=1)` over 20,000 filler rows refuses
  the whole table, and a `limit` or a server-side keyword filter gets past it.
- The whole corpus classified under a cost cap and the dev split scored against the people's labels,
  as in `../table/`.

## Needs

- `podman`, and `uv sync --all-extras` once. The example starts `docker.io/library/postgres:16`
  (podman needs the full registry name), loads the data, and removes the container when it ends,
  also on failure, Ctrl-C and SIGTERM. A container left by a killed run (SIGKILL) is removed by the
  next run.
- `ANTHROPIC_API_KEY` in the environment for the first classification; without it every database
  check still runs and the last line is `RESULT: skipped - ...`.
- The database URL is built from a random local port and kept in this process's environment only
  (`HUNCHES_PG_URL`); nothing is written to a file.

## Run

```bash
uv run python -m e2e.postgres.run
```

A pass ends with `RESULT: pass`.

## Cost

About 5 seconds of checks plus the container start (the first run also pulls the image). The
classification is cached in `e2e/.cache/`, shared with the other examples. Measured figures: see the
walkthrough README.

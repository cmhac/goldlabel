# Postgres with pgvector

Reference for a corpus in a Postgres table with a pgvector embedding column, searched by seed
phrases.

## What it shows

- `hn.PgCorpus(table="corpus", search="exact")`: the database ranks every row by cosine similarity.
- `hn.PgCorpus(table="corpus", search="index")` after `CREATE INDEX ... USING hnsw
  (embedding vector_cosine_ops)`: the index answers. Index search is approximate in general; for
  these 60 rows it returns the same ids and similarities as exact mode (a larger table may not).
- Seed phrases embedded by a stand-in embedder with hand-built vectors (`StandIn` in
  `../common/support.py`), so the similarities, bands and best seeds are written down in advance
  (`../common/expected.json`). With your own corpus, pass the embedding model that made your vectors.
- The whole corpus read without touching the vectors, classified under a cost cap, and the dev
  split scored against the people's labels, as in `../table/`.

## Needs

- `podman`, and `uv sync --all-extras` once. The example starts
  `docker.io/pgvector/pgvector:pg16` (podman needs the full registry name; index mode needs
  pgvector 0.8 or newer, which this image has), loads the data and removes the container when it
  ends, also on failure, Ctrl-C and SIGTERM.
- `ANTHROPIC_API_KEY` in the environment for the first classification; without it every database
  check still runs and the last line is `RESULT: skipped - ...`.

## Run

```bash
uv run python -m e2e.pgvector.run
```

A pass ends with `RESULT: pass`.

## Cost

A few seconds of checks plus the container start (the first run also pulls the image). The
classification is cached in `e2e/.cache/`, shared with the other examples.

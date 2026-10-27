# Table: files and DataFrames

Reference for a corpus that is a file or a DataFrame. No container, no database.

## What it shows

- The one common corpus (`../common/corpus.jsonl`, 60 posts) loaded through `hn.Table` from a CSV,
  JSONL and Parquet file (Parquet read by polars, and by pandas when polars is not installed), a
  polars DataFrame, a pandas DataFrame and a list of row dicts. Every form gives the same 60 ids.
- `hn.get_candidates` for the whole corpus, for keywords and regular expressions (an inline flag,
  ranking by distinct terms then total matches, `limit`), and for seed phrases (JSONL, Parquet and
  DataFrame carry vectors; a CSV cannot and is refused).
- Seed search uses a stand-in embedder with hand-built vectors (`StandIn` in `../common/support.py`),
  so it needs no key. With your own corpus, pass the embedding model that made your vectors.
- The whole corpus classified with a small model under a cost cap, then the dev split scored
  against the labels people made (`../common/gold.jsonl`, provenance in `../common/GOLD.md`).

## Needs

- `uv sync --all-extras` once. Run with `--with pyarrow` so the pandas Parquet form is checked
  (without it that form is reported as skipped by name).
- `ANTHROPIC_API_KEY` in the environment for the first classification. Without it, every candidate
  check still runs and the last line is `RESULT: skipped - ...`.

## Run

```bash
uv run --with pyarrow python -m e2e.table.run
```

A pass ends with `RESULT: pass`. A failed check stops with `RESULT: fail - <check>: expected <a>,
got <b>` and exit status 1.

## Cost

Candidate steps take a few seconds and cost nothing. The first classification of the 60 posts is a
few hundredths of a US dollar at most (model `anthropic:claude-haiku-5-5`); results are cached in
`e2e/.cache/`, so a rerun makes no model calls. Measured figures: see the walkthrough README.

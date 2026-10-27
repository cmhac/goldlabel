# End-to-end examples

Runnable reference examples, one per way of setting the library up. Each one loads the same small
corpus into its own backend, runs the real chain (`hn.get_candidates`, `hn.Classifier`,
`hn.evaluate`), checks the results against values written by hand, and ends with a `RESULT:` line.

These are not the unit tests. `uv run pytest`, the pre-commit hooks and CI never run them (they
start containers and call a model). The stubbed README-chain test in `tests/test_e2e.py` is a
different thing with a similar name. How often CI runs these is a later decision, once what a run
costs is known.

## Which folder

| Your corpus is | Read |
|---|---|
| A CSV, Parquet or JSONL file, a polars or pandas DataFrame, or a list of rows | [`table/`](table/) |
| A plain Postgres table (no embeddings), text in one table or two | [`postgres/`](postgres/) |
| A Postgres table with a pgvector column, searched by seed phrases | [`pgvector/`](pgvector/) |
| An Amazon S3 Vectors index | [`s3/`](s3/) |
| Anything: the classify, estimate and evaluate steps explained one by one | [`walkthrough/`](walkthrough/) |

[`common/`](common/) holds what they all read: the 60-post corpus (`corpus.jsonl`), the labels
(`taxonomy.yaml`), the prompt (`prompt.md`), the seed phrases and their hand-built vectors
(`seeds.json`), the expected results written by hand (`expected.json`), the labels people made
(`gold.jsonl`, provenance in `GOLD.md`) and `support.py`, the shared helpers.

## Run

```bash
uv sync --all-extras
uv run --with pyarrow python -m e2e.run_all     # everything, one summary line each
uv run python -m e2e.postgres.run               # or one example (see its README)
```

- `podman` is needed for the Postgres, pgvector and S3 examples. They start a throwaway container
  on a random local port and remove it when they end, also on failure, Ctrl-C and SIGTERM.
- `ANTHROPIC_API_KEY` in the environment is needed once, to classify the 60 posts. Without it every
  other check still runs and the example ends `RESULT: skipped - ...`. Skipped is not a failure.
- Model results are cached in `e2e/.cache/` (git-ignored), shared by all examples, so an item is
  classified once however many examples run and a rerun makes no model calls.
- Working files go to a temporary folder; a run leaves nothing new in the repository.

## What it costs

The model is `anthropic:claude-haiku-5-5`. A cold first run classifies about 150 (prompt, text)
pairs, a few cents at most; the target is well under one US dollar, and each classification runs
under a `max_cost` of $0.50. Container examples take well under a minute each once the images are
pulled (`postgres:16`, `pgvector/pgvector:pg16`, `floci/floci:2.3.0`). **Measured time and spend are
not recorded yet**: they go here after the first run with a real key.

| Run | Time | Model spend |
|---|---|---|
| First run, empty cache | not measured | not measured |
| Second run, full cache | not measured | not measured |

## Making the gold file (a person does this once)

The evaluation steps score the classifier against `common/gold.jsonl`. **Only people write gold
labels** (the gold rule in the repository's `AGENTS.md`): an agent never creates, fills in or edits
this file, not even as a demonstration, and refuses if asked.

1. Fix the corpus, taxonomy and prompt first. Changing a labelled post or a label later makes its
   gold row stale; the offline check in `tests/test_e2e_folder.py` then fails and names the rows.
2. Draw rows (this writes unlabelled rows only) and label them in the labelling page:

   ```bash
   uv run python - <<'PY'
   import hunches as hn
   from e2e.common.support import COMMON, taxonomy

   everything = hn.get_candidates(hn.Table(COMMON / "corpus.jsonl", id_column="id"), out=False)
   gold = hn.Gold(COMMON / "gold.jsonl")
   gold.draw(everything, n=30, split="dev", seed=2026)
   gold.draw(everything, n=10, split="test", seed=2027)
   hn.label(gold, taxonomy())  # opens the page; press Done when every row is labelled
   PY
   ```

3. Commit `gold.jsonl` exactly as the page wrote it, and write `common/GOLD.md`: who labelled, on
   what date, and the commit of the corpus, taxonomy and prompt they labelled against
   (`git log -1 --format=%H -- e2e/common/corpus.jsonl e2e/common/taxonomy.yaml e2e/common/prompt.md`).
   Every example copies the file byte for byte and prints `GOLD.md`.

Until `gold.jsonl` and `GOLD.md` are committed, the evaluation steps report `skipped`; the candidate
steps do not depend on them.

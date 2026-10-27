# Quickstart: validating the e2e examples

Prerequisites: `uv`, `podman` (Postgres, pgvector, S3 examples), `ANTHROPIC_API_KEY` in the
environment (the first classification only). `uv sync --all-extras` once.

## 1. Default checks stay offline

```bash
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
```

Expect: pass with no container tool, no key and no network. `tests/test_e2e_folder.py` fails if an
example folder, README link, public-name use or data agreement is broken. If `e2e/common/gold.jsonl`
does not exist yet, its checks report skipped with the reason.

## 2. One example, no key (candidate steps only)

```bash
uv run --with pyarrow python -m e2e.table.run
```

Expect: every form loads the same 60 ids; keyword, regex and seed checks pass; the model step is
reported `skipped` (no key, empty cache), the last line is `RESULT: skipped - ...`, exit 0.

## 3. One example with a key

```bash
ANTHROPIC_API_KEY=... uv run --with pyarrow python -m e2e.table.run
```

Expect: the estimate prints first (60 items, 0 cached, N live, a price that is not `?`), the run
stays under its cap, the dev evaluation prints with `labelled_by: hunches-ui` counts and the
`GOLD.md` provenance, `score=...`, `RESULT: pass`. Run it again: 0 live calls.

## 4. A container example

```bash
uv run python -m e2e.postgres.run
podman ps -a --filter label=hunches-e2e      # empty afterwards
```

Expect `RESULT: pass`, candidates equal to the table example's, and no container left. Interrupt
one with Ctrl-C and run `podman ps -a` again: still empty.

## 5. Everything

```bash
uv run --with pyarrow python -m e2e.run_all
```

Expect one line per example and `all: pass`. With no podman: the container examples fail naming
`podman`; with no key and a cold cache: they report skipped, not passed.

## 6. Human-only

1. After the corpus, taxonomy and prompt are approved: draw rows and label them in the labelling
   page (procedure in `e2e/README.md`); commit `gold.jsonl` and `GOLD.md` as written.
2. First real run: record the elapsed time and model spend in the walkthrough README.
3. Open `e2e/walkthrough/walkthrough.ipynb` in real Jupyter and in marimo or Colab.

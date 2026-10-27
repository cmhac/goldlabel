# Walkthrough: classify, estimate and evaluate

The detailed notebook for the part of the chain after you have candidates: draw gold rows, use the
labels people made, estimate the cost, classify under a spend cap, evaluate on dev, read the
disagreements, tune the prompt, band-sample, evaluate the test split once, price a larger run and
save the classifier. The other examples run these steps tersely against a file, Postgres and S3;
this one explains each.

It is a notebook only: `walkthrough.ipynb`, no stored outputs. It runs over the shared corpus in
`../common/`, copies `../common/gold.jsonl` byte for byte and prints its provenance
(`../common/GOLD.md`). It never writes a gold label.

## Needs

- `uv sync --all-extras` once.
- `ANTHROPIC_API_KEY` in the environment for the first classification. Without it, every cell up to
  the estimate runs and the next cell stops with `SKIPPED: set ANTHROPIC_API_KEY ...`; with the
  headless run that is reported as skipped, not as a failure.
- `../common/gold.jsonl`, made by a person in the labelling page. Until it is committed, the notebook
  stops at the gold cell with `SKIPPED: ... not made yet`.

## Run

Open it in Jupyter (`uv run jupyter lab` needs `uv run --with jupyterlab`), marimo or Colab, from
this folder (the paths are relative to it). Or run it headlessly with everything else:

```bash
uv run --with pyarrow python -m e2e.run_all
```

A failing cell fails the run; a missing key or gold file is reported as skipped.

## Cost

About 150 model calls on the first run (the whole corpus under the first prompt, the dev and test
rows and the 44 chosen candidates under the second prompt), results cached in `e2e/.cache/`, shared
with the other examples. At the listed price of `claude-haiku-5-5` ($0.10 per million input and
$0.50 per million output tokens, from secondary sources) that is about two cents; the target is
well under one US dollar. A rerun makes no model calls. **The measured time and spend are not
recorded yet**: the first run with a real key fills them in here.

# Sample

A tiny end-to-end run you can try on a fresh clone, with no API key and no setup beyond `uv`.

`walkthrough.py` (plain script; `# %%` marks the cells) and `walkthrough.ipynb` (the same cells for
Jupyter, marimo or Colab) walk the whole chain over `corpus.jsonl`: eight short posts with hand-built
2-D vectors, not real embeddings. **You** are the person who labels the gold rows; the classifier is a
crude keyword stand-in that gets some rows wrong on purpose, so there is something to review. Put
`ANTHROPIC_API_KEY` in the environment and a real model answers instead.

## Run it

```bash
git clone https://github.com/cmhac/goldlabel && cd goldlabel
uv sync
cd examples/sample
uv run python walkthrough.py  # the walkthrough; for the notebook: uv run --with jupyterlab jupyter lab walkthrough.ipynb
```

The script opens the labelling page twice (it prints the address if your browser does not open).
Press **Done** each time.

1. **dev** has three posts: label `layoff-1` as `layoff`, `burnout-1` and `burnout-2` as `burnout`.
2. **test** has two posts: label `layoff-2` and `layoff-3` as `layoff`.

Everything it writes goes to `.goldlabel/` (gold labels in `gold.json`, evaluations in `evals.jsonl`),
`results.jsonl` and `classifiers/`; all three are git-ignored.

## What to look at in the page

Run `uv run goldlabel label` (from this folder) once the script has finished:

- **Datasets and samples:** the default dataset with its `dev` and `test` samples and how many rows are
  labelled. Open `dev` for its rows; type an id such as `burnout-2` in **Jump to id** to open one row.
- **Evaluations:** under the rows, each evaluation of the sample with its score and the rows the
  classifier got wrong, next to your label. The stand-in calls any post that mentions work or a job a
  layoff, so `burnout-2` ("Working weekends...") is one of them.
- **Revise a label:** open a row, pick a different label, then go back to the sample. The evaluation is
  now marked **STALE**, because a row was revised after it ran. Run `uv run python walkthrough.py` again
  (nothing is pending, so it only re-evaluates) and a new, current evaluation appears. The row in
  `.goldlabel/gold.json` keeps what it said before in its `revisions`.
- **Many labels:** to see the text stay in view while a long label list scrolls (from 1024px wide), add
  thirty more labels to the `taxonomy` cell, for example `**{f"extra{i}": "unused" for i in range(30)}`
  inside the `labels` dictionary, and label a row again.

To start over, delete `.goldlabel`, `results.jsonl` and `classifiers/`.

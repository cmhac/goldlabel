---
name: goldlabel
description: "Use when doing content analysis over a corpus with the goldlabel Python library: finding candidate items with seed phrases (semantic search), keywords or regular expressions, or taking the whole corpus, classifying them with an LLM, building and checking a gold set of human labels, tuning the prompt, estimating cost, or reusing a saved classifier in a notebook or pipeline. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# goldlabel

`goldlabel` is a Python library for content analysis over a corpus: candidates come from seed-phrase semantic search, from keywords or regular expressions, or from the whole corpus, and an LLM classifier checked against a hand-labelled gold set then produces classified output. You build it step by step in one Jupyter notebook by calling plain functions; each result shows itself. There is no app and no status: **the state is the code and the files**.

```
pip install goldlabel            # extras: goldlabel[pg] pgvector, goldlabel[s3] S3 Vectors, goldlabel[rds] RDS IAM
```

## The procedure (a hard requirement)

Work through these six skills in this order, one at a time. Start at the first. Do not skip, merge or reorder them unless the user tells you to. Load the skill for the stage you are at.

1. `goldlabel-connect`: point at the data, confirm the connection and columns, reshape only if the user agrees.
2. `goldlabel-search-terms`: keywords, regular expressions or seeds, drafted with the user and approved.
3. `goldlabel-taxonomy`: read the corpus with the user and agree the labels.
4. `goldlabel-candidates`: run `gl.get_candidates(...)`, inspect the result, settle the list.
5. `goldlabel-tune`: classifier, gold set (people label), dev tuning, the test split, and what to do when its score is too low.
6. `goldlabel-run`: cutoff, estimate, the full run, and optionally saving the classifier.

**At the end of every stage, tell the user what comes next.** Recommending the next step is a hard requirement of this workflow, not a courtesy: users rely on it to learn the order and to notice when they are off it. Use this form:

> **Done: <stage>.** It produced <what>; you approved <what>. **Next: `goldlabel-<next>`**, which <one line>. Say "go" and I will start it.

After `goldlabel-run` say **Sequence complete** and name what is optional and still open. Each stage skill has the same four parts: an entry check, a numbered procedure, an exit check and a closing "Next". Optional steps are marked `(optional)` inside the stage they belong to; none is a stage of its own.

**Entry checks.** If a stage's entry check fails, say which earlier stage is unfinished, offer to run it, and continue only if the user tells you to skip it. **Repeating a stage.** Each stage says what must be re-run if it is repeated; tell the user.

## Write only goldlabel calls

In short: write only goldlabel calls. The notebook contains goldlabel calls and nothing else: no snapshot or cache of the data, no guard such as `if not path.exists()` or `if not gold.all.rows` around a library call, no helper function or class, no long constants, no code that loads a `.env` file, and no charts, deduplication, aggregates, exports or fact-check cells after the run. The library already caches model calls, so re-running `evaluate` or `classify` costs nothing. If something seems to need other code (a query for data the library cannot read, a reshaping step), stop, show the user exactly what you would write and why, and write it only after their yes. Do not put the taxonomy, the prompt or the seed and keyword lists in a file (YAML, markdown or CSV): they are variables in cells, unless the user explicitly tells you to use a file.

Use a Jupyter notebook (`.ipynb`) for the analysis. Write a `# %%` script only if the user says to. Drawing is safe to rerun: `gold.draw_sample(name)` draws only what its sample is missing. Evaluating the held-out test sample is **run-once**: tell the user which cell it is and run it once. Do not guard any cell.

## Hard rules

1. The gold rule above. Never write, edit, infer or auto-fill a gold label, never edit a gold file by any means, and never take a label from a model.
2. Never run the full classification without first showing the estimate (`clf.estimate(...)`: calls, cost, time; `cost ?` means the price is unknown, never read it as zero) and getting an explicit yes. Pass `max_cost=` when you do run it.
3. Never evaluate the held-out test sample to guide edits. Tune on the dev sample; the test sample is evaluated once, at the end, to report. If its score is too low and the user wants to keep tuning, the spent test sample joins the tuning set (`tuning = dev + test`) and people label a fresh one (`gold.draw_sample("test-2")`), but only after the user's explicit yes (see `goldlabel-tune`).
4. Never put an API key or a database URL in a notebook, script or any file. Keys and `GOLDLABEL_PG_URL` come from environment variables (environment variable names go in code, values never); `PgCorpus(url_env=...)` takes the variable's name. Do not load a `.env` file.
5. Ask the user at each decision point; do not decide for them: the brief (what counts as a match), the seeds (which phrases would be true of a match), `single` or `multi` labels, the label descriptions, the similarity cutoff, the target score, and whether to spend money on a full run.

## Where files go

`.goldlabel/` in the current directory by default (`gl.settings.root`, or the environment variable `GOLDLABEL_DIR`): `candidates.jsonl`, `gold.json`, `evals.jsonl` (every evaluation, kept as a history) and `cache/` (model calls and the cost ledger). The gold files and `evals.jsonl` always live there: there is no option to move them or to switch the log off. Candidates, results and the cache take a path to move their file; `cache=False` or `out=False` writes nothing. Commit the notebook; the library never runs git.

## References (load the one you need)

- `references/workflow.md`: the whole chain as the cells of one notebook, in order.
- `references/tuning.md`: reading `ev.disagreements`, changing one thing at a time, when to stop, the held-out test sample, the evaluation history.
- `references/running.md`: estimate, cost, `max_cost`, resuming, keys and database URLs, the band sample and the cutoff.
- `references/reuse.md`: saving a classifier bundle, importing it in a pipeline, recording the evaluation.

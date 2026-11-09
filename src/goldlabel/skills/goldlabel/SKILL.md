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

## Check progress first

`/goldlabel` is where a user starts whenever they do not know which skill to call. Before any stage, find out what they already have. Read their notebook or script (the calls in it) and only the file names and modification times in the storage folder (`.goldlabel/` by default). This check changes and runs nothing, and you never open gold*.json or evals.jsonl (an evaluation line holds row text, gold labels and model reasoning; for counts, ask the user or point them to the labelling page), and never read a key, a database URL or a .env.

| Stage | Evidence |
|---|---|
| 1 | a corpus: `gl.Table`, `gl.PgCorpus` or `gl.S3Corpus` |
| 2 | `seeds` and/or `keywords` variables (none if the user chose the whole corpus: ask) |
| 3 | a `gl.Taxonomy(...)` |
| 4 | a `gl.get_candidates(...)` call; `candidates.jsonl` |
| 5 | `gl.Classifier`, `gl.Gold` and `clf.evaluate` calls; `gold*.json` and `evals.jsonl` exist |
| 6 | `clf.estimate` and `clf.classify` calls; a saved classifier |

Tell the user what you found, stage by stage: **done** (name the evidence you saw), **unsure** (say why: a variable nothing uses, a cell that may not have run, a gold file that may belong to another notebook) or **not started**. Then name the stage to resume at, the first without evidence, and ask "start there?". Evidence is not consent: skip a stage only on the user's yes, and that stage's own entry check still applies. If they say "start over" or name a stage, follow them. Start at `goldlabel-connect` only when nothing is done. If stage 6 is done, say **Sequence complete** and offer what is optional (reusing the classifier, a second corpus, reviewing labels in the page).

Several `gold-<name>.json` files: ask which dataset they are working on. A notebook with anything other than goldlabel calls: say so and offer to clean it up; never delete it unasked.

## The procedure (a hard requirement)

Work through these six skills in this order, one at a time. Start at the stage the progress check names (the first, when nothing is done). Do not skip, merge or reorder them unless the user tells you to. Load the skill for the stage you are at.

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

## The stages in plain words

Use these to explain each stage before you start it; the stage skill has the steps.

- **`goldlabel-connect`** (1) Purpose: point goldlabel at the data and check it reads. Ask: what they want to find (the brief), where the data is, which columns hold the id and the text. Show: the first rows and your plain summary. Approval: the connection and any filter or reshaping you propose.
- **`goldlabel-search-terms`** (2) Purpose: choose how to narrow the data down to likely matches. Ask: which seed phrases, keywords or regular expressions fit the brief, or the whole corpus. Show: the list, and a sample of what keywords bring in. Approval: the list of terms.
- **`goldlabel-taxonomy`** (3) Purpose: agree the labels an item can get. Ask: `single` or `multi`, each label and its description, where two nearby labels draw their line. Show: the taxonomy and sample rows read together. Approval: exactly these labels, descriptions and mode.
- **`goldlabel-candidates`** (4) Purpose: build the list of candidate items. Ask: whether the list is right after reading a sample. Show: the sample and the counts. Approval: the candidate list, which stays fixed once gold rows are drawn from it.
- **`goldlabel-tune`** (5) Purpose: build the classifier and measure it against labels people wrote. Ask: how many gold rows, the target score, which one change to try next, when the prompt is final. Show: the evaluation and its disagreements. Approval: each prompt change, and the one test evaluation.
- **`goldlabel-run`** (6) Purpose: classify everything. Ask: the similarity cutoff, whether the estimate is acceptable, the `max_cost`. Show: the estimate (calls, cost, time) before the run, the results and errors after. Approval: an explicit yes to the full run.

## How to talk the user through a step

Say what the step is for, in plain words, before you do it, then show the result, not a description of it. Put the decision that is theirs to them, as a question, and wait for the answer: do not decide for them. Explain any term the first time you use it. One stage at a time. Then say what comes next, in the "Done" form above.

## The labelling and review page

People label, and review labels, in the labelling page. It can: list the datasets and samples in the storage folder, open a row, jump to a row by id, label the pending rows, revise a label or a note, and show each evaluation with its disagreements and a STALE flag. While a person labels, the page never shows a model's prediction.

- In a terminal the user runs `goldlabel label [NAME]` (`--dir` and `--port` are optional). If you cannot open a browser, give them the command; never say you opened the page when you did not.
- In the notebook, `gl.label(sample, taxonomy)` opens the rows of that sample still pending (`force_open_ui=True` walks every row, to review) and waits until they press Done. If the page is already running, it joins it.

```python
gl.label(dev, taxonomy)  # people label the pending rows of the dev sample
```

When a label looks wrong, or the user wants to change one: every revision of a gold label or note goes through the page. Tell them how to open it. A revised row keeps its earlier values, and an evaluation made before a revision is STALE: evaluate again (a new line in `evals.jsonl`; the old one is never rewritten). If the user says "just fix them", refuse as the gold rule says, point to the page, and offer other help.

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

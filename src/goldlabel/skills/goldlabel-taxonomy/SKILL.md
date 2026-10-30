---
name: goldlabel-taxonomy
description: "Use when the labels for a goldlabel classification are not decided yet: reading and searching the corpus to find what kinds of items there are, proposing labels with descriptions and the boundaries between similar ones, and agreeing the taxonomy with the user, either unattended with approval at the end or as a back and forth. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# Build the taxonomy by reading the corpus

Goal: a `taxonomy.yaml` the user has approved. You read and search the corpus yourself and propose; the user decides. Before this: `goldlabel-connect` and `goldlabel-search-terms`. After: `goldlabel-candidates` (or straight to `goldlabel-tune` if the candidates already exist).

## Ask first

1. The brief, if it is not already written down.
2. **How involved do they want to be?** (a) *Unattended*: you run the whole loop below and stop with one proposal for approval. (b) *Together*: you stop after each round with what you found and what you suggest, and they steer. Either way nothing is final until they say so.
3. `single` (each item exactly one label) or `multi` (an item can carry several). Their call, not yours. `off_topic` is always there, exclusive, and means "not a match"; do not define it.

## The loop

Repeat until the proposal stops changing (or, in the together mode, until the user says it is enough):

1. **Read broadly.** A random sample of the corpus, and the search results for the brief (keywords or seeds; see `goldlabel-candidates`). Read at least 30 items before the first proposal, and look at items from the whole range, not only the top.
2. **Read at the edges.** Near-misses and surprises: for seeds, the items just under the cutoff; for keywords, items that matched only one term; and items from the random sample that look related but are not.
3. **Write up what you found** in your notes: the kinds of items, how many of the sample each kind was, two or three quoted examples with their ids, and what you are unsure about.
4. **Propose or revise labels.** Each label gets a name and one or two sentences that say what it is and how it differs from the nearest label ("Offers a prize or payout in exchange for a fee or personal data. Not satire, and not a genuine promotion by a named brand."). Say where the boundary between each pair of nearby labels falls, with an example on each side.
5. **Test the boundaries.** Fetch more items for the boundary in question and say which side each falls on, in your notes. Change one thing at a time.

```python
import goldlabel as gl

sample = gl.get_candidates(corpus, limit=2000).sample(
    30, seed=1
)  # a random sample (a file or small table)
sample.rows[:5]

hits = gl.get_candidates(corpus, keywords=["ballot", "poll worker"], limit=200)
near = [r for r in hits.rows if r["terms_matched"] == 1][:20]  # matched only one term
```

For a seed list, the items just under a cutoff are `[r for r in candidates.rows if 0.60 <= r["max_similarity"] < 0.70]`.

## Save only what the user approved

Show the proposal as a table: label, description, the boundary note, two examples. Ask for approval, then write it:

```python
taxonomy = gl.Taxonomy(
    mode="single",  # or "multi", as the user chose
    labels={
        "scam": "Offers a fake prize or payout for a fee or personal data.",
        "satire": "Obvious parody of a scam; nobody is meant to be deceived.",
    },
)
taxonomy.write("taxonomy.yaml")
```

## What your reading is, and is not

Everything you sort while exploring is **notes**: in the conversation or in a notes file such as `taxonomy-notes.md`. It is not gold. Never write it to a gold file, never count it as a score, never describe it as labels, and never "label a few" so the classifier can learn from them: gold labels are written only by people, in the labelling page (`goldlabel-tune`). If the user asks you to turn your sortings into gold, refuse as the rule above says, and offer to open the labelling page.

Do not use items you read as worked examples inside the classifier prompt unless you check, later in `goldlabel-tune`, that they are not rows of the gold set.

## Ask, do not decide

The label names and descriptions, `single` or `multi`, merging or splitting labels, and when the taxonomy is good enough are the user's decisions. Offer a recommendation, with your reason, and wait.

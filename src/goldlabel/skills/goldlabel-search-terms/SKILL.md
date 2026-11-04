---
name: goldlabel-search-terms
description: "Use when deciding how to find the items that matter in a corpus with goldlabel: turning what the user wants to analyse into keywords, regular expressions or semantic-search seed phrases, choosing between them depending on whether the data has embeddings, keeping the approved terms as variables in the notebook, and trying the terms on a small sample before running them for real. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# Stage 2 of 6: Choose the search terms

Goal: a short list of keywords, regular expressions or seed phrases that the user has read and approved, tried on a few results, kept as a variable in a notebook cell.

## Entry check

- `corpus` works and the user has seen its first rows (stage 1), and the brief is written in the notebook.
- If any of this is missing, say which stage is unfinished (`goldlabel-connect`), offer to run it, and continue only if the user tells you to skip it.

## Procedure

Write only goldlabel calls. Anything else needs the user's yes, shown to them first.

1. Ask which kind of list, decided by the data and the user, never by you:
   - **Keywords or regular expressions**: no embeddings needed; literal and exact; cheap. Right for a distinctive vocabulary, and the only option for data without vectors.
   - **Seeds**: needs embeddings and the embedder that made them; finds items worded differently from your terms.
   - **The whole corpus**: no filter; right only when the corpus is already small or already filtered. The classifier reads every item, so the estimate in `goldlabel-run` matters. If the user picks this, there is nothing to draft: say so and go to the exit check.
2. Draft a proposal and say why each term is there; the user adds, removes and rewrites. Nothing you generate is final.
   - **Keywords**: 10 to 20 terms grouped by idea (the topic words, the slang, the misspellings the user knows). A plain string is a literal, case-insensitive term. For patterns use `regex=True` with the pattern written as it is, `(?i)` for case-insensitive (`(?i)vote[sd]?`), or compiled `re.Pattern` objects, which keep their own flags. A pattern that can match the empty string is refused; zero-width patterns such as `\b` still match every word, so never use one alone.
   - **Seeds**: 5 to 10 short sentences that would be true of a match, not keywords: what a matching item could say. Cover different wordings of the same idea; a seed that is too general pulls in junk.
3. Put the approved terms in a cell, as code, not in a file:

```python
seeds = ["I lost my job", "The company is cutting staff"]
keywords = ["ballot", "poll worker"]
```

4. Try keywords on a small sample before the real run. Seeds are tried for real in `goldlabel-candidates`, because that embeds them and shows the similarity bands; do not run a large seed search before the user has approved the seeds.

```python
hits = gl.get_candidates(corpus, keywords=keywords, limit=200)
hits.sample(10, seed=1).rows  # read them with the user: are these matches?

# regular expressions
rx = gl.get_candidates(corpus, keywords=[r"(?i)vote[sd]?"], regex=True, limit=200)

# a very large Postgres table: let the database do the matching
big = gl.get_candidates(corpus, keywords=["ballot"], server_side=True, limit=500)
```

5. Show ten results per term group and what they look like. Count how many results each term brings in and point out a term that brings in nearly everything or nearly nothing.

## Exit check

- The user approved the list of terms (or chose the whole corpus), and it is in a cell.
- For keywords, the user has read a sample of what they bring in.

If this stage is repeated (terms changed), re-run `goldlabel-candidates`. Gold rows already labelled stay valid, but tell the user that rows drawn from the old list may not represent the new one.

## Next

**Next: `goldlabel-taxonomy`.** Tell the user: the terms are chosen and approved, what kind of list it is, and that the next stage reads the corpus with them to agree the labels. Offer to start it.

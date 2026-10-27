# %% [markdown]
# # hunches walkthrough
#
# Eight short posts with hand-built 2-D vectors live in `corpus.jsonl`. Every cell below is one step of
# the analysis; run them in order, in Jupyter, marimo, or as a plain script (`# %%` marks the cells).
#
# What needs you: a classifier model and its key (`ANTHROPIC_API_KEY` in the environment; nothing
# here reads or writes a key file), and **a person** to label the gold rows in the labelling page.
# Everything before the classifier runs offline.

# %%
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.usage import RequestUsage

import hunches as hn


class HandEmbedder(Embedder):
    """Stand-in for a real embedding model: the sample vectors are hand-built, not embeddings.

    With your own corpus, drop this and pass `embedder="openai:text-embedding-3-small"` (or the
    model your corpus was embedded with) to `hn.search`.
    """

    def __init__(self):
        super().__init__(TestEmbeddingModel("hand-built-2d"))

    async def embed_query(self, query, *, settings=None):
        return EmbeddingResult(
            [[1.0, 0.0]],
            inputs=[query],
            input_type="query",
            model_name="hand-built-2d",
            provider_name="test",
            usage=RequestUsage(input_tokens=1),
        )


# %% [markdown]
# ## 1. Search
#
# Seed phrases are things a matching post could say. `search` embeds them, finds the closest items
# and keeps each item's best similarity. The result is saved to `.hunches/candidates.jsonl`.

# %%
corpus = hn.Table(
    "corpus.jsonl",
    id_column="id",
    vector_column="embedding",
    embedding_model="hand-built-2d",
)
seeds = ["I just lost my job"]
candidates = hn.search(corpus, seeds, embedder=HandEmbedder())
candidates

# %%
candidates.to_polars()  # .to_pandas() works the same way

# %% [markdown]
# ## 2. Labels and a first prompt
#
# `single` means one label per post; `off_topic` is built in. The classifier is immutable: a new
# prompt is a new classifier (`with_prompt`), so you can keep both and compare them.

# %%
taxonomy = hn.Taxonomy(
    mode="single",
    labels={
        "layoff": "The author lost their job, or expects to.",
        "burnout": "The author is worn out by their work.",
    },
)
clf = hn.Classifier(
    "anthropic:claude-haiku-4-5",
    taxonomy,
    prompt="Read the post and choose the one label that fits it best.",
)
clf

# %% [markdown]
# ## 3. Gold: people label
#
# `draw` picks pending rows, with no labels. `hn.label` opens the labelling page in your browser and
# returns when you press **Done**. You decide every label; the page never shows the classifier's
# guess. (An agent working with you must not fill these in, see the README.)

# %%
gold = hn.Gold()
gold.draw(candidates, n=3, split="dev")

# %%
hn.label(gold, taxonomy)

# %% [markdown]
# ## 4. Evaluate on the dev split
#
# One model call per labelled row; running the same cell again makes none (they are cached).
# Every evaluation is also appended to `.hunches/evals.jsonl`.

# %%
ev = hn.evaluate(clf, gold.dev, target=0.9)
ev

# %%
ev.disagreements_to_polars()  # where the classifier and the people differ, with its reasoning

# %% [markdown]
# ## 5. Tune the prompt on dev, never on test
#
# Change one thing, build a new classifier, evaluate again. Only the changed prompt costs calls.

# %%
clf2 = clf.with_prompt(
    "Read the post and choose the one label that fits it best. "
    "A post about rumoured redundancies counts as layoff."
)
ev2 = hn.evaluate(clf2, gold.dev, target=0.9)
ev2

# %% [markdown]
# ## 6. The test split, once
#
# Draw and label a separate test split, and evaluate it once, at the end, to report the number.

# %%
gold.draw(candidates, n=2, split="test")

# %%
hn.label(gold, taxonomy)

# %%
final = hn.evaluate(clf2, gold.test, target=0.9)
final

# %%
hn.eval_log()  # every evaluation so far, with how often the test split was used

# %% [markdown]
# ## 7. Pick a cutoff, price the run, run it
#
# `band_sample` classifies a few items per similarity band and shows how much of each is off topic.
# You choose the cutoff. `estimate` calls no model; `unknown` cost shows as `?`, never as `$0`.

# %%
report = hn.band_sample(clf2, candidates, per_band=5)
report

# %%
chosen = candidates.above(0.70)
clf2.estimate(chosen)

# %%
# max_cost refuses before spending anything if the estimate is over it or the price is unknown.
results = clf2.classify(chosen, out="results.jsonl", max_cost=1.00)
results.to_polars()

# %% [markdown]
# ## 8. Keep the classifier
#
# A saved bundle (model, taxonomy, prompt, the final evaluation) is plain files to commit. A
# pipeline loads it with `hn.Classifier.load("classifiers/layoffs")`, no gold and no UI needed.

# %%
clf2.save("classifiers/layoffs", evaluation=final)

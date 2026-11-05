# %% [markdown]
# # goldlabel walkthrough
#
# Eight short posts with hand-built 2-D vectors live in `corpus.jsonl`. Every cell below is one step of
# the analysis; run them in order, in Jupyter, marimo, or as a plain script (`# %%` marks the cells).
#
# What needs you: **a person** to label the gold rows in the labelling page. The classifier is a
# real model when `ANTHROPIC_API_KEY` is in the environment (nothing here reads or writes a key
# file); without it, a crude keyword stand-in answers instead, so the whole walkthrough runs offline
# and you can try the labelling page, the evaluations and the revisions without a key. When the
# script has run, `uv run goldlabel label` (from this folder) opens the same page on every dataset,
# to browse the rows, read the evaluations and revise a label.

# %%
import os

from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

import goldlabel as gl

LIVE = (
    "ANTHROPIC_API_KEY" in os.environ
)  # a real classifier, or the offline stand-in below


def keyword_stand_in():
    """A deliberately crude classifier that needs no key: any post that mentions work or a job
    is a layoff. It gets some rows wrong, which gives the evaluation something to show."""

    def answer(messages, info: AgentInfo):
        post = next(
            p.content
            for m in reversed(messages)
            for p in reversed(m.parts)
            if isinstance(p, UserPromptPart)
        )
        words = ("laid off", "job", "work", "cut")
        label = "layoff" if any(w in post.lower() for w in words) else "burnout"
        reply = {"reasoning": f"keyword match in: {post}", "labels": [label]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply)])

    return FunctionModel(answer, model_name="keyword-stand-in")


class HandEmbedder(Embedder):
    """Stand-in for a real embedding model: the sample vectors are hand-built, not embeddings.

    With your own corpus, drop this and pass `embedder="openai:text-embedding-3-small"` (or the
    model your corpus was embedded with) to `gl.get_candidates`.
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
# Seed phrases are things a matching post could say. `get_candidates` embeds them, finds the closest items
# and keeps each item's best similarity. The result is saved to `.goldlabel/candidates.jsonl`.

# %%
corpus = gl.Table(
    "corpus.jsonl",
    id_column="id",
    vector_column="embedding",
    embedding_model="hand-built-2d",
)
seeds = ["I just lost my job"]
candidates = gl.get_candidates(corpus, seeds=seeds, embedder=HandEmbedder())
candidates

# %%
candidates.to_polars()  # .to_pandas() works the same way

# %% [markdown]
# ## 2. Labels and a first prompt
#
# `single` means one label per post; `off_topic` is built in. The classifier is immutable: a new
# prompt is a new classifier (`with_prompt`), so you can keep both and compare them. (Offline, the
# stand-in ignores the prompt, so a new prompt will not move its score; a real model can.)

# %%
taxonomy = gl.Taxonomy(
    mode="single",
    labels={
        "layoff": "The author lost their job, or expects to.",
        "burnout": "The author is worn out by their work.",
    },
)
clf = gl.Classifier(
    "anthropic:claude-haiku-4-5" if LIVE else keyword_stand_in(),
    taxonomy,
    prompt="Read the post and choose the one label that fits it best.",
)
clf

# %% [markdown]
# ## 3. Gold: people label
#
# `draw_sample` picks pending rows, with no labels, and is safe to rerun: it draws only what is
# missing. `gl.label` opens the labelling page in your browser and
# returns when you press **Done**. You decide every label; the page never shows the classifier's
# guess. (An agent working with you must not fill these in, see the README.) Label the three posts
# by what they say: the first is a layoff, the other two are burnout.

# %%
gold = gl.Gold(candidates)
dev = gold.draw_sample("dev", n=3)

# %%
gl.label(dev, taxonomy)

# %% [markdown]
# ## 4. Evaluate on the dev split
#
# One model call per labelled row; running the same cell again makes none (they are cached).
# Every evaluation is also appended to `.goldlabel/evals.jsonl`, with the rows it got wrong. Run
# `uv run goldlabel label` and open the "dev" sample to read them there: change a label you got
# wrong, and the evaluation is marked STALE until you run it again.

# %%
ev = clf.evaluate(dev, target=0.9)
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
ev2 = clf2.evaluate(dev, target=0.9)
ev2

# %% [markdown]
# ## 6. The test split, once
#
# Draw and label a separate test sample, and evaluate it once, at the end, to report the number.

# %%
test = gold.draw_sample("test", n=2)

# %%
gl.label(test, taxonomy)

# %%
final = clf2.evaluate(test, target=0.9)
final

# %%
test  # its summary says how often this held-out sample was evaluated

# %% [markdown]
# ## 7. Pick a cutoff, price the run, run it
#
# `band_sample` classifies a few items per similarity band and shows how much of each is off topic.
# You choose the cutoff. `estimate` calls no model; `unknown` cost shows as `?`, never as `$0`.

# %%
report = clf2.band_sample(candidates, per_band=5)
report

# %%
chosen = candidates.above(0.70)
clf2.estimate(chosen)

# %%
# max_cost refuses before spending anything if the estimate is over it or the price is unknown.
# (Offline, the stand-in has no price, so there is nothing to cap.)
results = clf2.classify(chosen, out="results.jsonl", max_cost=1.00 if LIVE else None)
results.to_polars()

# %% [markdown]
# ## 8. Keep the classifier
#
# A saved bundle (model, taxonomy, prompt, the final evaluation) is plain files to commit. A
# pipeline loads it with `gl.Classifier.load("classifiers/layoffs")`, no gold and no UI needed.

# %%
clf2.save("classifiers/layoffs", evaluation=final)

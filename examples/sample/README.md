# Sample

`walkthrough.ipynb` (Jupyter, marimo, Colab) and `walkthrough.py` (the same cells with `# %%` markers)
walk the whole chain over `corpus.jsonl`: eight short posts with hand-built 2-D vectors, not real embeddings.
Search and the first prompt run offline; classifying needs `ANTHROPIC_API_KEY` in the environment, and
the gold rows are labelled by a person in the labelling page. Run it from this folder; files go to
`.goldlabel/` (git-ignored).

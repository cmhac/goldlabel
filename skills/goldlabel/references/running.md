# Running the classifier on the candidates

## Choose the cutoff with the user

The similarity cutoff decides which candidates are classified. Sample each band and look at how much of it is off-topic:

```python
report = gl.band_sample(clf, candidates, per_band=30, seed=1)
report  # per band: n, off_topic, rate; and the cost
report.to_polars()
```

This is a classification run, not an evaluation (not logged, uses no gold). Show the table and ask the user where to cut. The cutoff is a plain number:

```python
selected = candidates.above(0.70)
len(selected.rows)
```

## Estimate first, always

```python
est = clf.estimate(selected)
est  # n, cached, live, dollars (or "cost ?" when the price is unknown), seconds
```

Show the user the estimate, in words: how many items, how many calls are live, the cost (or that it is unknown), and the time. **Do not start the full run until they say yes.** `est.dollars` is `None` when the price is unknown (for example the first run of a model, with no priced sample to extrapolate from, or `cache=False`); never read that as zero. In that case say so, run a small slice first to get a priced sample, and ask again:

```python
sample = clf.classify(selected.sample(20, seed=1))
clf.estimate(selected)
```

## The full run

```python
results = clf.classify(selected, out="results.jsonl", max_cost=1.5 * est.dollars)
results  # rows with labels, reasoning, run; cost; errors
results.errors  # items that failed; they are returned, never raised
```

- `out=` is required for a real run: rows are appended as each completes, so a crash or an interrupted cell loses nothing. Run it again with the same `out=` and only the missing ids are classified (those with a successful row under the same classifier digest are skipped; rows from another prompt are re-classified).
- `max_cost` raises `CostLimit` before starting if the estimate is over it, stops (resumable) if the spend crosses it, and refuses when the price is unknown. Set it a little above the estimate (1.5 times is reasonable) and tell the user the number. With an unknown price you cannot set it; that is a second reason to get a priced sample first.
- Errors: a 401 or 403 from the provider, or several API errors in a row, stop the run with an exception. Finished rows are already in `out`, so fix the cause (a missing key, a rate limit) and run the same call again.
- `gl.cost()` shows the running total across runs from the ledger in the cache directory (`?` if any price is unknown).
- For long runs in a script, `progress=True` prints one updating line; in a notebook it updates in place.

## Keys and database URLs

Never write a key, token or database URL into a notebook, script, `.env` file you create, or any file you commit. Provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) and the database URL (`GOLDLABEL_PG_URL`, or the variable named by `PgCorpus(url_env=...)`) must already be in the user's environment. If a call fails because one is missing, tell the user which variable to set and stop; do not ask them to paste the value into the chat or the notebook. The library never loads a `.env` file and never touches the keyring.

## Paths

`out=` for a result, `cache=` for the model-call cache (a directory; `False` for none, which also gives up resume and repeat-call savings), `gl.settings.root` or `GOLDLABEL_DIR` for the default `.goldlabel/`. Do not write outside the project folder unless the user asked.

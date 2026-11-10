# Quickstart: validate `gl.get_methodology`

Prerequisite: `scripts/dev-setup.sh` has run. No key, network or browser is needed.

## 1. Automated

```bash
uv run pytest tests/test_methodology.py tests/test_candidates.py tests/test_classifier.py tests/test_corpus.py tests/test_public_api.py tests/test_docstrings.py -n0
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
```

Expect: green; `tests/test_methodology.py` builds a gold file and an `evals.jsonl` by hand and compares the text to hand-written strings.

## 2. By hand on the sample (needs a person and a real key, so Chris does this)

1. In `examples/sample/`, run `walkthrough.py` through `clf2.classify(...)` as the README describes (a person labels in the page).
2. Add a cell:

   ```python
   m = gl.get_methodology(
       candidates=candidates, gold=gold, classifier=clf2, results=results
   )
   print(m)  # the Markdown
   m.warnings  # () on a clean run
   ```

3. Check, against `.goldlabel/candidates.meta.json`, `.goldlabel/gold.json` and `.goldlabel/evals.jsonl`: every number and name in the text appears in one of them (SC-002).
4. Run the cell again: identical text (SC-003). Run with `include_gold_table=False`: no table, nothing else changes.
5. Open `results.jsonl`: every line has `run`, `run_model` and `run_at`. The text's *Run* section gives the same model, the first and last `run_at`, and the cutoff you passed to `above`.
6. Evaluate `test` a second time under a new prompt: the text now says the test sample was evaluated 2 times with 2 prompts (SC-005).
7. In `goldlabel label`, revise one `dev` label: the text flags the `dev` evaluation as predating a revision.
8. `git status` shows no gold or log file touched by the call (SC-006).

## 3. Needs a human

The wording read by a person who did the analysis: does it say what they did, in words they would put in a story? Agents cannot judge that.

# 01 — Record pre-006 behaviour as fixtures; baseline size

Spec: FR-4, SC-4, SC-5. **Run this on the unmodified pre-006 code**, before task 02 removes anything.

**Do**
- Create `tests/fixtures/pre006/` holding a tiny project written by the *current* code, using stubbed models only (`FunctionModel`, a fake embedder returning fixed 3-dimensional vectors):
  - `cache/`: one classification entry written by `classifier.classify` (taxonomy with two labels, `mode: multi`, a one-line prompt, one text) and one seed-embedding entry written by `candidates.embed_seeds`; plus `cost.json` as the code wrote it.
  - `seeds.csv`, `candidates.jsonl` (+ `candidates.meta.json`), `taxonomy.yaml`, `prompt.md`, `gold.jsonl` (labelled dev and test rows, plus one pending-looking row if the old format allows one), `results.jsonl` (rows with and without `run`), and a `corpus/` for the local backend (`items.jsonl`, `meta.json`, `vectors.npy`, 4 items).
  - `expected.json`: the values the new code must reproduce, recorded from the old code: for that classification call the exact `system_prompt(...)` string, the `cache_key(...)` hex, and `run_digest(...)`; for the seed embedding the cache key; for the local corpus one search (query vector, floor 0.60) with the ids and similarities.
  - `README.md` in that folder: the commit the fixtures were generated at (`git rev-parse HEAD`), how each file was made, and the one-off script used. The generator script is **not** committed as code (it only works on the old code); paste it into the README.
- Write `tests/test_pre006_fixtures.py` asserting the fixtures are well-formed and `expected.json` matches what the *current* code computes from them. Later tasks add their own assertions that the new code reproduces these values.
- Record the baseline in the task report and in `tests/fixtures/pre006/README.md`: `find src/hunches -name '*.py' | xargs wc -l | tail -1` (11,588 at the time the spec was written) and the list of test files.

**Tests**: only the fixture sanity test above. Expected values here are recorded from the old code on purpose; this is the one place that rule is waived.

**Not in this task**: any change under `src/`.

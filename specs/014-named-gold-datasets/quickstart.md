# Quickstart / validation: 014

## Automated (agent)

```bash
uv sync --all-extras
```

```bash
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
```

What the suite proves (tests named in `plan.md`):

1. Rerun safety: over 200 candidates, `draw_dev()` twice leaves 50 dev rows; `draw_test()` and `draw_test("test-2")` add 50 each, disjoint; `draw_dev(n=80)` adds 30; `draw_dev(n=30)` adds none.
2. Same rows for two people: two fresh roots and the same candidates give the same dev ids; another dataset name gives different ids.
3. Pass scope: with 50 labelled dev and 50 pending test rows, the test Sample's server state says total 50, sample `test`, and never serves a dev id.
4. Test once: these are refused, each with zero `FunctionModel` calls and no log line:
   - a test sample with a pending row;
   - a spent test sample under a second prompt;
   - `dev + test_2` with "test-2" unspent.

   An identical rerun returns the result and adds no line.
5. Fold by `+`: `dev + test` with "test" spent has 100 rows, and the gold file is byte-identical before and after.
6. Two datasets: the same id in both, separate files and locks; B's test evaluation leaves A's "test" unspent.
7. Old files: the pre-006 fixtures and a hand-written pre-014 log (no `samples`, one `test_folded` event) load; "test" in that log is spent.
8. End to end: `tests/test_e2e.py` runs the README chain with the new calls (labelling by the simulated human over HTTP), including `tuning = dev + test` and "test-2". It then runs the whole chain again and checks that the gold file and log are byte-identical and that no model call was made (SC-001).
9. Drift: no doc or skill example uses a removed name or a draw `seed=`.

## Needs a human

- Open the labelling page in a real browser for a dev Sample and a test Sample. The row line should name the sample, the count should be the pass only, and Back should work within the pass.
- Run `examples/sample/walkthrough.ipynb` in real Jupyter twice from the top. The second run should draw nothing, write no log line and make no live call.

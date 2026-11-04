# Quickstart / validation: 014

## Automated (agent)

```bash
uv sync --all-extras
```

```bash
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
```

What the suite proves (see the tests named in `plan.md`):

1. Rerun safety: `draw_dev()` twice over 200 candidates leaves 50 dev rows; `draw_dev(n=80)` adds 30; `draw_dev(n=30)` adds none (SC-001).
2. Same rows for two people: two fresh roots, same candidates, same dev ids; a different name gives different ids (SC-003).
3. Pass scope: 50 labelled dev + 50 pending test, the test Sample's server state says total 50, split `test`, never a dev id (SC-002).
4. Test refusal: a test Sample with one pending row raises in `clf.evaluate` with zero `FunctionModel` calls and no log line (SC-004).
5. Two datasets: same id in both, separate files, separate locks, A's fold eligibility unchanged by B's test evaluation (SC-005).
6. Drift: no doc or skill example calls `.draw(`, a draw `seed=`, `gl.label(gold`, `gl.evaluate(` or `gl.band_sample(` (SC-006).
7. End to end: `tests/test_e2e.py` runs the README chain with the new calls, labelling done by the simulated human over HTTP, then runs the draw, label and evaluate calls a second time and checks the gold file is byte-identical and no model call was made (SC-001).

## Needs a human

- Open the labelling page in a real browser for a dev Sample and a test Sample: the row line names the split, the count is the pass only, Back works within the pass.
- Run `examples/sample/walkthrough.ipynb` in real Jupyter twice from the top: the second run draws nothing.

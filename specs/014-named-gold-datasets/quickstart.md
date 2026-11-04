# Quickstart / validation: 014

## Automated (agent)

```bash
uv sync --all-extras
```

```bash
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
```

What the suite proves (the tests are named in `plan.md`):

1. **Rerun safety.** Over 200 candidates:
   - `draw_sample("dev")` twice leaves 50 rows.
   - `draw_sample("test")` and `draw_sample("test-2")` add 50 each, with no id in common.
   - `draw_sample("dev", n=80)` adds 30; `n=30` then adds none.
2. **Same rows for two people.** Two fresh roots with the same candidates give the same "dev" ids. Another dataset name gives different ids.
3. **Pass scope.** With 50 labelled "dev" rows and 50 pending "test" rows, the "test" Sample's server state says total 50 and sample `test`, and never serves a "dev" id.
4. **Always logged, never twice.**
   - Every evaluation writes one line.
   - An identical rerun writes none and makes zero `FunctionModel` calls.
   - A second prompt writes a line, and the summary says "evaluated 2 times (2 prompts)".
   - There is no `log` argument, and a `GoldSet` is refused.
5. **Combining.** `dev + test` has 100 rows, and the gold file is byte-identical before and after. Evaluating it writes one line naming both samples. Samples of two datasets are refused.
6. **Two datasets.** The same id can be in both, with separate files and locks. B's evaluations leave A's counts at zero.
7. **Old files.** The pre-006 fixtures and a hand-written pre-014 log load. That log has no `samples` and one `test_folded` event, and its "test" count is right.
8. **End to end.** `tests/test_e2e.py` runs the README chain with the new calls, with labelling done by the simulated human over HTTP, including `tuning = dev + test` and "test-2". It then runs the whole chain again and checks that the gold file and log are byte-identical and that no model call was made (SC-001).
9. **Drift.** No doc or skill example uses a removed name or a `seed=` on `draw_sample`.

## Needs a human

- Open the labelling page in a real browser for a "dev" Sample and a "test" Sample. Check that the row line names the sample, the count covers only the pass, and Back works within the pass.
- Run `examples/sample/walkthrough.ipynb` in real Jupyter twice from the top. On the second run, check that it draws nothing, writes no log line and makes no live call.

# Quickstart: validating 012

1. `uv run pytest tests/test_label_page.py tests/test_gold_rule.py tests/test_label_server.py tests/test_e2e.py -n0` passes.
2. By hand, in a scratch directory: draw rows, label them all with `gl.label`, run `gl.label(gold, taxonomy)` again: one line, no browser. Run `gl.label(gold, taxonomy, force_open_ui=True)`: the page opens. (Human check; a browser is never launched in tests.)
3. `gl.label(gold, taxonomy, block=False)` raises `TypeError`.
4. `uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest` pass.

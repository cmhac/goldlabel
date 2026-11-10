# Quickstart: check feature 019

```bash
uv run ruff check                      # 0 findings, with D, DOC201, DOC501 on
uv run ruff format --check
uv run ty check
uv run pytest tests/test_docstrings.py -n0
uv run pytest
```

Red/green for the rules (scratch file outside the repo, so nothing is committed): copy it into `src/goldlabel/` temporarily, or run `ruff check --config pyproject.toml --force-exclude <file>`; expect failures for a public function with no docstring (`D103`), a partial `Args:` (`D417`), and a raise with no `Raises:` (`DOC501`); delete the file and see 0 findings.

By hand (SC-003): in a notebook, `help(gl.Classifier.with_prompt)` and answer: replace or append (replace); is the original changed (no); what else does the model get (labels, mode rule, `off_topic`, reasoning instruction); are cached results reused (no).

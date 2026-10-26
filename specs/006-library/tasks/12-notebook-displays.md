# 12 — Notebook displays (`_repr_html_`) and `to_pandas`

Spec: "The pieces" intro, FR-12, FR-13. IPython calls `_repr_html_` for notebook output ([integrating docs](https://ipython.readthedocs.io/en/stable/config/integrating.html)); verify against the installed IPython only if you need to run one, otherwise call the methods directly. **Do not add IPython as a dependency.**

**Do**
- `src/hunches/_html.py`: tiny helpers (`table(columns, rows, cap)`, `bars(values)`, `warning(text)`, `details(...)`), all text through `html.escape`. **No foreground or background colours**: inherit from the notebook theme; use `currentColor`, `opacity` and borders with `currentColor` at low opacity. State is always words as well as shape (`PASS`/`FAIL`, `?`, `WARNING`). Row-capped tables (default 50) end with "N more".
- `_repr_html_` on: `Candidates` (count, per-band bars, capped warning), `Taxonomy` (labels and descriptions), `Classifier` (model, labels, 12-line prompt preview, digest, recorded evaluation if any), `Predictions`, `Estimate`, `Gold`/`GoldSet`, `Evaluation` (metrics, per-label table, PASS/FAIL, source counts, a bounded disagreement list), `EvalLog`, `BandReport`, `Cost`. Plain `__repr__` stays as built in each task.
- `.to_pandas()` on the table-like results (`Candidates`, `Predictions`, `GoldSet`, `Evaluation.disagreements` via a method, `EvalLog`, `BandReport`): `import pandas` lazily; if missing raise `ImportError("pandas is not installed: pip install pandas")`. No pandas dependency in `pyproject.toml` (dev group only, for the test).

**Tests (red first)**: item text `<script>alert(1)</script>` and `&` appear escaped in every table-like repr; no `color:`, `background` or `#rrggbb`/`rgb(` in any output (regex over the output of every object); every object returns a string with its key numbers (hand-checked counts); `cost ?` and a `WARNING` for unknown price; the row cap line; bars have text counts beside them; `to_pandas` returns the right shape when pandas is installed (dev group) and the right error when `sys.modules['pandas'] = None`.

**Not in this task**: the labelling page's own HTML/CSS (task 14).

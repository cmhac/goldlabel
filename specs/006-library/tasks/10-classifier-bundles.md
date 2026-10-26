# 10 — Classifier bundles: `save` and `load`

Spec: "`Classifier`" (`save`/`load`), FR-21, FR-22.

**Do**
- `clf.save(dir, evaluation=None)`: writes `classifier.yaml` (`model` only), `taxonomy.yaml`, `prompt.md`, and, when given an `Evaluation`, `evaluation.json` (`split`, `n`, `score` and `metric`, the full `metrics`, `digest`, `date`, number of rows by source). Creates the directory. Overwrites its own files only; leaves anything else in the directory alone. Text files end with a newline so diffs are clean.
- `Classifier.load(dir, *, cache=None)`: reads the bundle; `.evaluation` is the parsed `evaluation.json` or `None`; if `evaluation.digest` differs from the loaded classifier's `digest`, emit a `UserWarning` saying the recorded evaluation no longer matches this prompt/model/taxonomy. The cache location is never part of the bundle.
- The module-in-a-shared-place form needs no code; make sure it works (the docstring shows `classifier = hn.Classifier(...)` in a module imported elsewhere).

**Tests (red first)**: save → load round trip gives an equal `digest` and equal labels; evaluation attached and read back; editing `prompt.md` by hand then loading warns once; a missing `evaluation.json` is fine; loading a bundle in a script with no gold file, no UI and a `FunctionModel` classifies new items and writes to `out` (FR-22); `load(..., cache=False)`; the directory's unrelated files survive a second `save`.

**Not in this task**: any change to how `evaluate` logs.

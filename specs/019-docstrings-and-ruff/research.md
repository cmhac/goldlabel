# Research: 019 docstrings and ruff

All measured on 2026-11-10 with the installed `ruff 0.17.3` (pinned by `uv.lock`) against `src/` on this branch, and `ruff rule` / `ruff config` for the option text. Raw counts, not memory.

## R1. Which rules and which style

**Decision**: `select = ["D", "DOC201", "DOC501"]`, `[tool.ruff.lint.pydocstyle] convention = "google"`.

- `D` with the Google convention (stable): 119 findings today (35 `D102`, 19 `D205`, 19 `D209`, 16 `D105`, 11 `D103`, 9 `D100`, 5 `D101`, 5 `D107`). `D417` (every argument described) is part of the convention; it fires only when an `Args:` section exists.
- NumPy style gives 140 findings (24 extra `D401`) and PEP 257 145; Google reads best in an editor hover and `help()`, and its `Args:`/`Returns:`/`Raises:` headings are what `D417`/`DOC201`/`DOC501` look for. Alternatives rejected: NumPy (longer, underlined headings), PEP 257 (no argument checks).
- `DOC201` (missing `Returns`) and `DOC501` (missing `Raises`) are **preview** in 0.17.3 (`ruff rule DOC201`). `preview = true` with `explicit-preview-rules = true` enables only the codes named in `select`, so no other preview rule turns on. `uv.lock` pins ruff, so a preview change arrives only with a deliberate upgrade.
- Today they report 121 findings: 71 on public functions (47 functions), 50 on private ones (23 of them in the private modules `_label`, `_html`, `_sync`).

## R2. Private code

**Decision**: per-file-ignore `DOC201`/`DOC501` and `D` for `src/goldlabel/_*.py`; keep them on for private helpers in public modules.

Ruff cannot tell a private function from a public one for the `DOC` rules, so the ~27 private helpers in public modules (`_hit`, `system_prompt`, ...) get a `Returns:`/`Raises:` line each. `[tool.ruff.lint.pydoclint] ignore-one-line-docstrings = true` would skip them (54 findings left, all in multi-line docstrings) but would also let a public one-line docstring with a return value pass. Strict was asked for: keep it `false`; if the private-helper burden turns out noisy in implementation, flipping it is a one-line change recorded in the task note.

## R3. What ruff does not catch (tested with a scratch file)

| Case | Result |
| --- | --- |
| public function, no docstring | `D103` fails |
| `Args:` lists only some arguments | `D417` fails |
| raises `ValueError`, no `Raises:` | `DOC501` fails |
| **docstring with `Returns:` but no `Args:` section at all, function has arguments** | **passes** (`D417` only checks an `Args:` section that exists) |

**Decision**: one small test, `tests/test_docstrings.py`, walks the public callables of `goldlabel.__all__` with `inspect` and asserts that each one with parameters (other than `self`/`cls`) has an `Args:` section. It is the only check that closes the gap; the same walk asserts a docstring exists on every public callable, which names the offender in the failure.

## R4. Dunder methods and `__init__`

**Decision**: ignore `D105` (16, almost all `__repr__`/`_repr_html_`/`__len__`-style) and `D107` (5; Google style documents constructor arguments in the class docstring, an `Attributes:`/`Args:` section there). Document `Sample.__add__` by hand: it is how a spent test sample joins tuning, a public operation. The audit in task T03 lists any other public dunder that does something a reader would not guess.

## R5. Scope outside `src/`

`uv run ruff check` runs on the whole repo; tests, examples, scripts and specs are exempt via `per-file-ignores` (`D`, `DOC`), in the style of the existing `"examples/**" = ["B018"]` entry. Measured at implementation (T02), not assumed.

## R6. The `with_prompt` text (FR-001)

Read from `classifier.py` `system_prompt()`: `prompt.strip()`, blank line, `Labels:` list of `- name: description`, `- off_topic: ...`, the single/multi-label rule, the `off_topic` never-combined rule, the reasoning instruction. `with_prompt` is `dataclasses.replace(self, prompt=text)`: a new `Classifier`, same model, taxonomy and cache. The cache key hashes `system_prompt(...)` (`Classifier._key`/`digest`), so a changed prompt misses the cache for every item.

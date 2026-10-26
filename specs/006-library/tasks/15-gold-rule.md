# 15 — The gold rule: canonical text and run-time placement

Spec: "The gold rule" (all of it), FR-24 (library part).

**Do**
- `src/hunches/gold_rule.md` (package data): exactly two sections, `## Short` and `## Full`, whose bodies are copied **verbatim** from the spec's blockquotes (strip the `>` prefixes and keep the bold). Check `uv_build` ships it (same verification as task 14).
- `hunches/_gold_rule.py` (or inside `gold.py`): load the file with `importlib.resources`, expose `GOLD_RULE_SHORT` and `GOLD_RULE_FULL`; export both from `hunches/__init__.py`.
- Place the **Short** form in everything the agent sees when it runs code that touches gold: `repr(Gold)` and `repr(GoldSet)` (a last line), the return value's repr of `Gold.draw`, the text `hn.label` prints when it starts, and the message of every exception raised from `gold.py`/`_label.py` (a small `GoldError(ValueError)` base, text + two newlines + the short rule). Not in `_repr_html_` output (it would clutter notebooks; the plain `repr` is what an agent's tool output usually shows; if a harness shows the HTML repr, note it in the report).
- Do not put the rule in the labelling page.

**Tests (red first)**: `GOLD_RULE_SHORT`/`FULL` are non-empty, the Short form is under 400 characters, and the Full form contains the phrases `not negotiable`, `refuse` and `import`; the Short form appears verbatim in `repr(Gold(...))`, `repr(gold.dev)`, `repr(gold.draw(...))`, the captured stdout of `hn.label(..., open_browser=False, block=False)`, and `str()` of an error from `Gold.import_rows` with a duplicate id; a test that parses `specs/006-library/spec.md` blockquotes and compares them to the file so the spec and the file cannot drift.

**Not in this task**: the skill, steering file, instruction block (task 16, which extends the consistency test).

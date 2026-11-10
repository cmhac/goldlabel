# Tasks: Docstrings that explain every public function, enforced by ruff

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [quickstart.md](quickstart.md)
**Rules**: write docstrings only; no behaviour, signature or name change (FR-010); never touch `gold_rule.md`, `_gold_rule.py` or any way to set a label; `uv run ruff check`, `ruff format --check`, `ty check`, `pytest` pass before each commit (pre-commit enforces it); commit per task group as `019/Tnnn: ...`.

**Gate before T001**: run `/ponytail-review` on spec, plan and this file (constitution Principle III); apply its findings. After T020: `/ponytail-review` and `/ponytail-debt` on the diff.

**Docstring standard** (apply in every task below): one-line summary, blank line, then `Args:` (meaning, allowed values, units), `Returns:`, `Raises:` (only what is raised on purpose), and a plain sentence for each effect: files written and where, live model calls and cost (`max_cost`, `estimate`), network or database reads, a page opened, "returns a new X; the original is unchanged". Plain words, no spec numbers, no agent jargon; explain a domain term (gold set, sample, seed) once or point to the class that does. Lookalike names say how they differ. Cross-check any statement about behaviour against the code, not memory.

**Ruff is turned on last (T016)** so every earlier commit stays green; T002-T015 write docstrings that already satisfy it. Check each module as you go with `uv run ruff check --preview --select D,DOC201,DOC501 --config "lint.pydocstyle.convention='google'" src/goldlabel/<file>.py`.

## Phase 1: Setup

- [ ] T001 Re-measure on the pinned ruff and record the baseline in the "Audit record" section below: count of public callables with no docstring (script in the plan's research R-section: walk `goldlabel.__all__` with `inspect`), and the `D` and `DOC201`/`DOC501` findings per file for `src/` (expected today: 31 of 68, 119, 121). Also list every public dunder in the exported classes (`__add__`, `__len__`, `__iter__`, ...) and mark which need a hand-written docstring.

## Phase 2: User Story 1 - `with_prompt` (P1, the issue)

**Goal**: `help(Classifier.with_prompt)` answers replace-or-append and the rest of FR-001.
**Independent test**: SC-003 by reading; plus the one-off check in T003.

- [ ] T002 [US1] In `src/goldlabel/classifier.py` write the `Classifier.with_prompt` docstring (FR-001): replaces, not appends, the instruction text; the label list with descriptions, the one-label/every-label rule, the `off_topic` rule and the reasoning instruction are always added after it (`system_prompt()`); returns a new `Classifier` with the same model, taxonomy and cache, the original unchanged; a changed prompt means the next `classify`/`evaluate` calls the model again for each item (cache key hashes the whole system prompt); `Args:` `text`; `Returns:`. Write `with_taxonomy` in the same commit, as its lookalike, saying which part of the prompt it changes.
- [ ] T003 [US1] Check the two docstrings against behaviour with a throwaway script in the scratchpad (not committed): `clf.with_prompt("B")` has `prompt == "B"`, `clf.prompt` unchanged, `digest` differs, and `system_prompt("B", taxonomy)` ends with the lines the docstring lists. Fix the text, not the code, if they disagree. Commit T002 with the audit-record row for both methods.

## Phase 3: User Story 2 - every public callable (P1)

**Goal**: no public callable lacks a docstring (31 today); every existing one passes the FR-002 audit. Tasks are one per file so they can run in parallel.
**Independent test**: after each task, its file is clean under the ruff command above, and its audited callables are listed in the audit record with "gap found / filled" or "ok".

- [ ] T004 [P] [US2] `src/goldlabel/classifier.py`: the rest of `Classifier` (`classify`/`aclassify`, `estimate`, `evaluate`/`aevaluate`, `band_sample`/`aband_sample`, `save`/`load`, `digest`), `Predictions` (`errors`, `labels`, `to_polars`, `to_pandas`), `Estimate`, `CostLimit`; class docstrings list their fields (FR-003). Say what a cache hit costs, that failures are returned as rows and not raised or cached, and that `evaluate` always appends to `evals.jsonl` except an identical rerun.
- [ ] T005 [P] [US2] `src/goldlabel/candidates.py`: `Candidates` (`above`, `bands`, `top_seeds`, `write`, `to_polars`, `to_pandas`), `get_candidates`/`aget_candidates` (`seeds` vs `keywords` vs neither, `limit`, `server_side`), `read_seeds`; say what each band is.
- [ ] T006 [P] [US2] `src/goldlabel/gold.py`: `Gold` (`draw_sample`, `label`, `pending`, `all`, `import_rows`, `__getitem__`), `Sample` (`path`, `rows`, `counts`, `to_polars`, `to_pandas`, and `__add__`), `GoldSet`; say how `label`, `pending` and `all` differ and that `Sample` is read-only. State only what the code does; do not describe a way for code to set a label (Principle I) and do not reword the gold rule: refer to `GOLD_RULE_SHORT`.
- [ ] T007 [P] [US2] `src/goldlabel/evaluation.py`: `Evaluation` (`score`, `passed`, `write`, `disagreements_to_polars`, `disagreements_to_pandas`), `BandReport`; say how `score` and `passed` differ, what `passed` compares against, and where `write` writes.
- [ ] T008 [P] [US2] `src/goldlabel/search.py`: `Table`, `S3Corpus`, `PgCorpus` (class docstrings with constructor arguments, `where=` in each backend's form, what is read and what is never written), their public methods, and the module docstring. Largest file (43 callables); split into a commit per class if it gets long.
- [ ] T009 [P] [US2] `src/goldlabel/taxonomy.py`, `src/goldlabel/metrics.py`, `src/goldlabel/cost.py`, `src/goldlabel/settings.py`: `Taxonomy` (`names`, `write`, the label/mode fields), the metric functions that are public, `cost` and `Cost` (price unknown shows `?`; `max_cost` refuses), the `settings` object and `root`/`resolve`.
- [ ] T010 [P] [US2] `src/goldlabel/_label.py`: the exported `label` (what opens, when nothing is pending it prints one line and returns the labelled rows, `force_open_ui`, what a person sees, what is returned) and the other functions DOC201/DOC501 flag there; `src/goldlabel/cli.py`: the module and `main`, and the help text of `goldlabel install` and `goldlabel label` (the console's own `--help`, which is what a non-agent user reads); read each once as someone who has never seen the skills.
- [ ] T011 [P] [US2] `src/goldlabel/__init__.py`: the module docstring says how to read the docs (`help(gl.Classifier)`, hover in an editor) in one line; check `GOLD_RULE_*` and `GoldError` have a docstring a person can read (`_gold_rule.py` text unchanged).
- [ ] T012 [US2] Walk every lookalike pair from the spec (`with_prompt`/`with_taxonomy`, `Gold.label`/`pending`/`all`, `Evaluation.score`/`passed`, `write` on `Candidates`/`Evaluation`/`Taxonomy`) and write the one-sentence difference into the audit record (SC-004); fix a docstring that does not say it.
- [ ] T013 [US2] Fill the audit record for every one of the 37 callables that had a docstring before (ok, or the gap and the fix); confirm the count of callables without a docstring is 0 with the T001 script.
- [ ] T014 [US2] Fill private helpers in public modules that ruff's `DOC201`/`DOC501` flag (about 27, research R2): a `Returns:`/`Raises:` line each; no new prose beyond that.

## Phase 4: User Story 3 - ruff enforces it (P1)

**Goal**: a new undocumented or incomplete public docstring fails `ruff check` (and the Args test); nothing else changes.
**Independent test**: the red/green checks of `quickstart.md`.

- [ ] T015 [US3] Write `tests/test_docstrings.py` first (Principle IV): walk `goldlabel.__all__` and, for classes, `vars(cls)` public methods and properties (the same walk as T001); assert a docstring exists and, when the callable has parameters beyond `self`/`cls`, an `Args:` heading; the failure message names `Class.method`. Put the docstring standard from this file in the module docstring. Run it before T016-era edits are all in: it must fail on every still-undocumented callable (red), then pass after T004-T014 (green).
- [ ] T016 [US3] In `pyproject.toml` add under `[tool.ruff.lint]`: `select = ["D", "DOC201", "DOC501"]`, `preview = true`, `explicit-preview-rules = true`, `ignore = ["D105", "D107"]`; `[tool.ruff.lint.pydocstyle] convention = "google"`; extend `per-file-ignores` with `"tests/**"`, `"examples/**"`, `"scripts/**"`, `"specs/**"` and `"src/goldlabel/_html.py"`, `_frame.py`, `_sync.py`, `_gold_rule.py` set to `["D", "DOC"]` (keep the existing `examples/**` `B018`). `_label.py` is not exempt: it holds the exported `label`. If the lint selects more than the listed codes, tighten it. Run `uv run ruff check` on the whole repo: 0 findings. If one of tests/examples/scripts/specs still reports, extend its ignore, not the code.
- [ ] T017 [US3] Fix the layout findings left (`D205` summary line not followed by a blank line, 19; `D209`, 19) by hand or `ruff check --fix --select D209`; then `uv run ruff format`; confirm only docstring whitespace changed (`git diff --stat` and a read).
- [ ] T018 [US3] Red/green of the rules (spec User Story 3), outside the committed tree: copy the scratch file from research R3 into `src/goldlabel/`, confirm `ruff check` fails for no docstring, partial `Args:` and an unlisted `raise`, delete it, confirm 0 findings; record the three messages in the audit record. Note in the record that a docstring with no `Args:` section at all is caught only by `tests/test_docstrings.py` (research R3).
- [ ] T019 [US3] Add the two-line convention to `AGENTS.md` under Conventions (FR-011): public docstrings are for a person with no agent, Google style with `Args:`/`Returns:`/`Raises:` and the effects, enforced by ruff `D`, `DOC201`, `DOC501` and `tests/test_docstrings.py`. Add one line to the "Current state" paragraph: 019 implemented, closes issue #31. `CLAUDE.md` is the symlink; `tests/test_docs.py` must still pass.

## Phase 5: Polish

- [ ] T020 Run the full checks (`uv run ruff check`, `ruff format --check`, `ty check`, `pytest`); `uv build` wheel unchanged in contents; walk SC-001 to SC-005 and record each as met; confirm the diff changes no signature, name or behaviour (`git diff` on `src/` shows docstring lines, `pyproject.toml`, tests, `AGENTS.md`, specs only) and `git diff -- src/goldlabel/gold_rule.md src/goldlabel/_gold_rule.py` is empty.
- [ ] T021 `/ponytail-review` and `/ponytail-debt` on the diff; apply findings; push `claude/stoic-bardeen-rgigyw`. Do not open a PR unless asked.

## Dependencies and parallelism

- T001 first. T002-T003 (US1) next and alone: they are the issue and the smallest shippable slice.
- T004-T011 touch different files and run in parallel; T012-T014 follow them; T015 is written before them (red) but committed with the last docstring batch so no commit is red.
- T016-T018 after T014 (ruff must be green on `src/` before it is switched on); T019-T021 last.
- MVP: T001-T003 (the issue). Full scope: all.

## Audit record (filled by T001, T003, T012, T013, T018)

| Item | Result |
| --- | --- |
| Baseline (T001) | _public callables / without docstring / D findings / DOC findings_ |
| `with_prompt` / `with_taxonomy` (T003) | |
| `Gold.label` / `pending` / `all` (T012) | |
| `Evaluation.score` / `passed` (T012) | |
| `write` on `Candidates` / `Evaluation` / `Taxonomy` (T012) | |
| The 37 previously documented callables (T013) | _one line each: ok or gap + fix_ |
| Ruff red/green messages (T018) | |

---

description: "Task list for 009: workflow agent skills and a one-command installer"
---

# Tasks: Workflow agent skills and a one-command installer

**Input**: `specs/009-agent-skills-installer/` (spec, plan, research, data-model, contracts, quickstart)

**Tests**: required by Constitution Principle IV: each code task writes the failing test first, shows
it failing for the right reason, then makes it pass; expected values are written by hand.

**Rules for every task**: one commit named `009/TNNN: ...` on the assigned branch; `uv run ruff
check`, `uv run ruff format --check`, `uv run ty check`, `uv run pytest` pass before the commit;
never write, edit or infer a gold label; no `docker`; no new dependency. `[P]` = touches different
files from the other `[P]` tasks in the same phase. Ponytail was applied while drafting; the user
waived `/ponytail-review` of spec, plan and tasks for this feature.

## Phase 1: Foundation (blocks everything)

- [x] T001 Amend the constitution through the `/speckit-constitution` skill with the user's approval already given (2026-10-30): Principle VI allows `gold.fold_test()` plus a fresh test split on the user's explicit yes (agents MUST NOT fold without it); Stack and Agent packaging record the one console command `goldlabel` (installer only) and skills at `src/goldlabel/skills/`; bump to 1.2.0; Principle I and `src/goldlabel/gold_rule.md` stay byte-identical (check with `git diff` and `tests/test_gold_rule.py`). Fix `AGENTS.md` ("no console script", Layout, Current state) in the same commit. Files: `.specify/memory/constitution.md`, `AGENTS.md`.
- [ ] T002 Move the skill into the package. Red first: in `tests/test_skills.py` change `SKILL_DIR`/`ROOT / "skills"` paths to `src/goldlabel/skills/` and parametrise the front-matter, gold-rule (`GOLD_RULE_FULL` verbatim in the body, `GOLD_RULE_SHORT` at the end of the description), description length (<= 1024), name == folder and code-block tests over every folder under `src/goldlabel/skills/` (so later stage skills are checked automatically); add a test that a built wheel lists `goldlabel/skills/goldlabel/SKILL.md` (build to `tmp_path` with `uv build --wheel -o`). Then `git mv skills/goldlabel src/goldlabel/skills/goldlabel`, add `"skills": ["./src/goldlabel/skills"]` to `.claude-plugin/plugin.json`, update path mentions in `README.md`, `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md` (and the block-equality test in `tests/test_docs.py`), `tests/test_docs.py`; remove the empty root `skills/`. Run `claude plugin validate .` and report the result (unchecked if it cannot run). Files: `src/goldlabel/skills/goldlabel/**`, `.claude-plugin/plugin.json`, `README.md`, `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md`, `tests/test_skills.py`, `tests/test_docs.py`.

**Checkpoint**: one skill, in the package, same tests green, wheel ships it.

## Phase 2: User Story 4 - the fold (Priority: P1)

**Goal**: `Gold.fold_test()` per data-model.md and plan Design; the library half of FR-013 to FR-015.

**Independent test**: `tests/test_gold.py` and `tests/test_evaluation.py` cases below, then the e2e case.

- [ ] T003 [US4] Red first, then implement. In `tests/test_gold.py`: hand-built gold file with two labelled test rows, one labelled dev row and an `evals.jsonl` holding a test-split evaluation line: after `fold_test()` the two rows have `split == "dev"` and `id`, `text`, `labels`, `labelled_by`, `labelled_at` equal to the hand-written originals (compare the raw JSON lines minus `split`), the dev row is untouched, `evals.jsonl` gained `{"event": "test_folded", "rows": 2}`; `GoldError` when a test row is pending (message tells the user to finish labelling), when there is no labelled test row, when the log has no test evaluation since the last fold, and on a second call. In `tests/test_evaluation.py`: `eval_log()` keeps evaluation rows in `.rows` and fold events in `.folds`; `_test_line` counts only test evaluations after the last fold and states the fold in words ("40 test rows folded into dev"); `to_polars()` columns unchanged. Implement `Gold.fold_test(log=None)` in `src/goldlabel/gold.py` (reuse `_read`/`_write`/`resolve`; `model_copy(update={"split": "dev"})`) and `EvalLog.folds` in `src/goldlabel/evaluation.py`. Check for a circular import before importing `eval_log` into `gold.py`. Files: `src/goldlabel/gold.py`, `src/goldlabel/evaluation.py`, `tests/test_gold.py`, `tests/test_evaluation.py`.
- [ ] T004 [US4] Extend `tests/test_e2e.py` (simulated human labelling over HTTP, `FunctionModel`, counting calls): after the existing chain, draw and label a test split, evaluate it, `fold_test()`, assert `gold.test` is empty and `gold.dev` grew by that many rows with identical labels, draw a fresh test split (`draw(split="test")` excludes the folded ids), it is pending, `evaluate` on it is not called until labelled, and `eval_log()` reports zero test evaluations since the fold. Also add a test in `tests/test_gold_rule.py` (or `test_gold.py`) that greps `src/goldlabel/` for writers of `labels`: only `_label.py` and `Gold.import_rows` set them, and `cli.py` (once it exists) imports nothing from `goldlabel.gold`. Files: `tests/test_e2e.py`, `tests/test_gold_rule.py`.

## Phase 3: User Story 1 - the installer (Priority: P1)

**Goal**: `goldlabel install` per `contracts/cli.md`.

**Independent test**: `tests/test_cli.py` with `tmp_path` project and a fake home (`monkeypatch.setenv("HOME", ...)` and `Path.home`), no network.

- [ ] T005 [US1] Red first, then implement `src/goldlabel/cli.py` and `[project.scripts] goldlabel = "goldlabel.cli:main"` in `pyproject.toml`. Tests (hand-written expected paths, from `contracts/cli.md` and research R1): per agent and scope the exact folders, `codex copilot` writes `.agents/skills` once and says so, `kiro` also writes `.kiro/steering/goldlabel.md` whose text equals `steering_text()` and `.kiro/steering/goldlabel.md` in the repo equals it too, a second run reports "up to date" and changes no mtime, a modified installed `SKILL.md` exits 1 unless `--force`, `--dry-run` writes nothing, `--dir PATH` writes the folders and rejects an agent name with it, unknown agent exits 1 and lists valid names, no agent exits 2, a symlinked target folder is refused, a failure during copy (monkeypatch `os.replace`) leaves no `.tmp` folder, the output ends with the per-agent next step (Copilot `/skills reload`, Kiro `resources` line), and `import goldlabel` does not put `goldlabel.cli` in `sys.modules`. Use `importlib.resources.files("goldlabel") / "skills"`; one `shortcut:` comment on the agent table. Files: `src/goldlabel/cli.py`, `pyproject.toml`, `uv.lock`, `tests/test_cli.py`, `tests/test_public_api.py`.
- [ ] T006 [US1] Wheel check: add a test (build wheel to `tmp_path`, mark it so it is skipped when `uv` is missing) that the wheel contains `goldlabel/cli.py`, every skill folder and a `goldlabel` console script in `entry_points.txt`; run quickstart step 3 once by hand (install the wheel in a clean venv, `goldlabel install claude --dir`) and record the output in the commit message. Files: `tests/test_cli.py`.

**Checkpoint**: MVP: the installer works with the existing overview skill.

## Phase 4: Stage skills (Priorities: P1, P2)

**Goal**: the six skills of `contracts/skills.md`. `tests/test_skills.py` (parametrised in T002) already checks front matter, rule text, description length, and that code blocks use public names, so each task is: write the skill, run the drift tests, fix what they print. Every skill states the decisions it asks the user and its next skill. Examples use only real signatures: check each against `help(gl.X)` / the source before writing it (Constitution "External APIs").

- [ ] T007 [P] [US2] Write `src/goldlabel/skills/goldlabel-connect/SKILL.md`: connect, `corpus.check()`, first rows, column checks, extras on import errors, environment variables only, reshape with a read-only-source polars script that names the first bad row and never drops or repairs rows. Add a test in `tests/test_skills.py` that runs the skill's shaping and `Table` examples against a tiny hand-built CSV and a fake `psycopg` check where feasible (reuse `tests/test_corpus.py` fixtures). Files: skill file, `tests/test_skills.py`.
- [ ] T008 [P] [US2] Write `src/goldlabel/skills/goldlabel-search-terms/SKILL.md` (keywords vs regex vs seeds vs whole corpus by embeddings; `read_seeds`, `seeds.csv`, `regex=True`, `(?i)`, `server_side`; proposals the user edits). Files: skill file.
- [ ] T009 [P] [US3] Write `src/goldlabel/skills/goldlabel-taxonomy/SKILL.md`: the unattended loop (random samples, keyword/seed searches, near-misses, a write-up with quoted ids), the optional back and forth, one change at a time, stop for approval, `Taxonomy(...).write("taxonomy.yaml")` only after approval, exploration notes go in a notes file or the conversation and never under a gold path, nothing hand-sorted becomes a prompt example that is a gold row. Add a test that its example `Taxonomy` code runs and loads back. Files: skill file, `tests/test_skills.py`.
- [ ] T010 [P] [US2] Write `src/goldlabel/skills/goldlabel-candidates/SKILL.md` (`get_candidates`, `bands`, `top_seeds`, `sample`, rewording seeds rather than the classifier, no bands for keyword or whole-corpus lists, the similarity cutoff is the user's). Files: skill file.
- [ ] T011 [US4] Write `src/goldlabel/skills/goldlabel-tune/SKILL.md` per `contracts/skills.md` (gold advice, `gl.label` for people only and the refusal with the offered help, import unchanged, dev loop, flipped rows, stop rules, prompt-example/gold-row check, the single final test evaluation, the fold only after the user's explicit yes, fresh test split labelled by people). Update `src/goldlabel/skills/goldlabel/references/tuning.md` so the fold is the recommended path and the old "fresh test split" paragraph agrees; update `src/goldlabel/skills/goldlabel/references/workflow.md` section 4 for the same. Add a drift assertion that the words "explicit yes" and `fold_test` appear in this skill and that `fold_test` appears in no other skill without the same sentence. Files: skill file, the two references, `tests/test_skills.py`.
- [ ] T012 [P] [US5] Write `src/goldlabel/skills/goldlabel-run/SKILL.md` (estimate first, `cost ?` with a warning, explicit yes, `max_cost=`, `clf.classify`, `clf.save`, reuse). Update the overview `src/goldlabel/skills/goldlabel/SKILL.md` to list the six stage skills and which to load when, keeping its hard rules and where-files-go sections. Files: skill file, overview skill, `src/goldlabel/skills/goldlabel/references/running.md` if it duplicates.

**Checkpoint**: all seven skills installable; `goldlabel install all` writes seven folders per target.

## Phase 5: User Story 6 and the documents (Priority: P3)

- [ ] T013 [US6] README: the install section leads with `goldlabel install <agent>` (and `uvx goldlabel install`), then a short manual section (copy a skills folder, or paste the instruction block); delete the install recipes for the four agents and every "unverified" marker; point to the fold in the walkthrough text where it says the test split is evaluated once. Update `docs/agent-instructions.md` and `.kiro/steering/goldlabel.md` only where they mention paths or the test split (the gold rule text stays verbatim; run the drift tests and paste what they print). Update `tests/test_docs.py` (README blocks use public names, no "unverified", mentions of `goldlabel install`). Files: `README.md`, `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md`, `tests/test_docs.py`.

## Phase 6: Polish

- [ ] T014 Run quickstart steps 1 to 5 and record the outputs; `uv run pytest` full, `uv build` (wheel contains the skills and script), `claude plugin validate .`; mark the 009 entry in `AGENTS.md` "Current state" (what a human must still do: install in each agent and list skills, the gold-rule refusal trial in each, Kiro custom-agent `resources`, Codex/Copilot real discovery, `copilot skill add` unverified); run `/ponytail-debt` and list the `shortcut:` comments; final report with red/green evidence, check outputs, deviations (the waived `/ponytail-review`), the Ponytail line and what only a human can do. Files: `AGENTS.md`, `specs/009-agent-skills-installer/quickstart.md` (record outputs only).

## Dependencies and order

T001 -> T002 -> (T003 -> T004) and (T005 -> T006) can run in either order after T002 -> T007..T012 (T007 to T010 and T012 are independent; T011 after T003) -> T013 -> T014.

## Implementation strategy

MVP is T001, T002, T005, T006: the installer plus the existing overview skill. Then the fold (T003, T004), then skills in the order of the workflow (T007 to T012), then the README (T013). Stop and ask the user only for a decision this spec does not already settle.

## Deliberately skipped

Everything in the spec's "Deliberately skipped" list; plus a root `skills/` copy, a sync script, an installed-files manifest, and any test that starts a real agent.

# Tasks: Rename the library to goldlabel

**Input**: `/specs/008-rename-goldlabel/` (spec.md, plan.md, research.md, data-model.md, contracts/rename-map.md, quickstart.md)

**Tests**: required by the constitution (red first, hand-written expectations). One commit per task, `008/TNN: ...`, on the assigned branch. Four tasks is the fewest that finish the feature: the rename is one mechanical change, so it is not split by story; splitting it would leave the repository broken between commits.

## Phase 1: Gate

- [x] T001 Amend the name in the constitution through `/speckit-constitution` as a PATCH (1.1.0 to 1.1.1): `hunches` to `goldlabel`, `hunches.label`/`hunches._label` to the new names, `HUNCHES_DIR` to `GOLDLABEL_DIR`, `.hunches/` to `.goldlabel/`, `hn.settings.root` to `gl.settings.root`, `src/hunches/...` and `skills/hunches/` paths to the new ones, and nothing else; no principle is weakened. The user's instruction "run speckit-tasks, then implement and open a PR" after reading the plan, which names this amendment as the precondition, is the approval; record that in the commit message and in the constitution's sync report. Stop and ask if the amendment would change any word other than the name. Files: `.specify/memory/constitution.md` (only via the skill).

## Phase 2: Legacy stamp, then the rename

Red tests are written and shown failing inside the task that makes them pass: pre-commit runs `uv run pytest` before every commit and `--no-verify` is forbidden, so a commit of only-failing tests is impossible.

- [x] T002 [US3] Legacy stamp first, still under the old package name (every check green at the commit). Red: in `tests/test_gold.py` a hand-built gold file with three rows all stamped `hunches-ui` whose summary reads `goldlabel-ui 3, imported 0, unstamped 0`, and a mixed file with one `goldlabel-ui`, one `hunches-ui`, one `imported`, one unstamped reading `goldlabel-ui 2, imported 1, unstamped 1` (hand-computed), both leaving the file's bytes unchanged; the same legacy case for the provenance count in `tests/test_evaluation.py`; `tests/test_label_server.py`, `tests/test_gold_rule.py`, `tests/test_e2e.py` and `tests/test_bundle.py` expect the new page stamp and the new summary key. Show them failing. Green: add one small helper in `src/hunches/gold.py` that maps the legacy stamp `hunches-ui` to `goldlabel-ui` for counting, used by `GoldSet._summary` and by the provenance count in `src/hunches/evaluation.py` (`evaluation.py:178`), with a one-line comment saying why (existing gold files keep their provenance); `src/hunches/_label.py` and the `labelled_by` comment in `gold.py` write `goldlabel-ui`. Show them passing, then the four checks.
- [x] T003 [US1] [US2] [US3] [US4] The mechanical rename, one commit. Red first: `tests/test_no_old_name.py` (walks `git ls-files`; fails on any case-insensitive `hunches` outside the allowlist, which the test lists by exact path: `specs/001*` to `specs/008*`, `tests/fixtures/pre006/README.md`, `uv.lock` excluded by never containing it after `uv lock`, and per file the exact legacy tokens `hunches-ui` in `src/goldlabel/gold.py`, `tests/test_gold.py`, `tests/test_evaluation.py` and `tests/test_label_server.py`, and the migration note in `README.md`), a settings test in `tests/test_settings.py` (with `GOLDLABEL_DIR` unset and `HUNCHES_DIR=/x` set the root is `.goldlabel`), a hand-written `evals.jsonl` line with `"hunches": "0.1.0"` that `read_log` loads (`tests/test_evaluation.py`), and the full new rule text pinned inline in `tests/test_gold_rule.py` (the old text with the name replaced, written out by hand). Show them failing. Green: (1) `git mv src/hunches src/goldlabel`, `skills/hunches skills/goldlabel`, `.kiro/steering/hunches.md .kiro/steering/goldlabel.md`. (2) One scripted replacement over `git ls-files` minus all of `specs/`, `tests/fixtures/pre006/README.md`, `uv.lock`, `skills-lock.json`, longest token first: `HUNCHES_`→`GOLDLABEL_`, `X-Hunches-Token`→`X-Goldlabel-Token`, `hunches`→`goldlabel`, `Hunches`→`Goldlabel` (check each hit), then `\bhn\b`→`gl` in README, `AGENTS.md`, `docs/`, `skills/goldlabel/`, `examples/` and tests (review every hit); put back the legacy `hunches-ui` in the helper and in the legacy-stamp tests, and `HUNCHES_DIR` in the one settings test. (3) `src/goldlabel/gold_rule.md` takes the amended wording from T001 (name only). (4) `pyproject.toml`, `.claude-plugin/{plugin,marketplace}.json`, `plugin.json` (names and repository URL `https://github.com/cmhac/goldlabel`), README install commands (`goldlabel@goldlabel`, `cmhac/goldlabel`), `.github/workflows/ci.yml` (`GOLDLABEL_TEST_PG_URL`), `.gitignore` (`.goldlabel`). (5) `README.md` gets a short "Moving from hunches" note: install name, import and alias, `GOLDLABEL_DIR` / `GOLDLABEL_PG_URL`, move `.hunches/` to `.goldlabel/`. (6) `docs/agent-instructions.md` and the README block stay equal; `examples/sample/walkthrough.py` and `.ipynb` stay equal; `AGENTS.md` ("Current state" gets one line for 008, history stays) with `CLAUDE.md` still a symlink. (7) `uv lock`, `uv sync --all-extras`, `uv run ruff check --fix`, `uv run ruff format`. Show the new tests and the whole suite green.

## Phase 3: Verify and report

- [x] T004 Run the quickstart (`specs/008-rename-goldlabel/quickstart.md`) steps 1 to 7 and report their real output summaries: the four checks, the leftover-name test, `uv build` and the wheel listing, a clean-venv install and `import goldlabel` / failing `import hunches`, the three drift tests, the legacy-stamp test, the migration check. Run `/ponytail-review` on the diff and `/ponytail-debt`, fix what they find. Then push and open the pull request (the user asked for one), following the repository's PR template if there is one, and list the human-only items (plugin reinstall and gold-rule refusal trial in each agent, the README install commands marked unverified, the labelling page in a real browser, renaming the GitHub repository before or with the merge, reserving `goldlabel` on PyPI) in the PR body.

## Dependencies

T001 → T002 → T003 → T004. No task is parallel: each changes files the next one reads.

## Independent test per story

- US1: clean-venv install of the wheel, `import goldlabel`, README chain (`tests/test_e2e.py`), no `hunches/` in the wheel.
- US2: `tests/test_gold_rule.py`, `tests/test_skills.py`, `tests/test_docs.py` and the pinned rule text.
- US3: the legacy-stamp tests (T002), and the old-log-line and settings tests (T003).
- US4: `tests/test_no_old_name.py`, `claude plugin validate .` if available.

## Implementation strategy

MVP is the whole feature; there is no useful half-rename. Legacy stamp with its red/green (T002), one mechanical change with its red/green (T003), verification and PR (T004).

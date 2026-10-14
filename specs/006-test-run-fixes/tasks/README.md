# Tasks for 006 — fixes and improvements from the first test run

Read `../spec.md` first (the source of truth; its "Resolved decisions" Q1–Q7 are final), then your task file. If a task file and the spec disagree, flag it instead of guessing; if the spec is wrong or incomplete, say so and fix it in the same change. A task does only what its file says: later tasks own later behaviour. **Never implement beyond your task.**

## Rules for every task

- Repo rules in `/home/user/hunches/CLAUDE.md` apply: minimal implementation (a plain `if`, no base class, registry or plugin system), no real LLM, AWS, keyring or database in tests, check every Textual and Pydantic AI API against the installed version (Textual 8.2.8 at the time of writing) and the current docs before using it, do not code from memory. Every screen works at 80×24; `tests/test_sizes.py` covers every screen and modal at 80×24, 100×30 and 120×36, so add anything new to it.
- **Red/green TDD, shown in the work.** Write the failing tests first and run them to see them fail for the right reason; then implement until they pass. Report, per behaviour, the failing run (command and failure message) and the passing run. Expected values are hand-written in the tests, never derived by running the code under test. Layout assertions use widget regions (`widget.region`), not screenshots.
- `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest -m "not ui"` pass before every commit. For a task that touches a screen, modal, `app.py`, `hunches.tcss` or anything a screen reads, also run the relevant UI test files (targeted, e.g. `uv run pytest tests/test_search_screen.py tests/test_sizes.py`) during development and the full `uv run pytest` once at the end. Report the actual output summaries.
- One commit per task on branch `claude/funny-ritchie-args3k`, message `006/NN: …` (plus the attribution lines the session gives). Push the branch after each commit. Do not open a PR.
- Update or delete existing tests the task breaks, in the same commit. Do not weaken an assertion to make it pass; say why when one must change.
- Anything the spec marks "verify in the task" is verified against the installed Textual and its docs, and the result is written into the spec (a short "Verified in task NN" note under the relevant item) in the same commit.
- Final report per task: what changed, files touched, red/green evidence, check outputs, deviations from the spec, anything only a human can do. Never fake a human check.

## Order

| # | Task | Spec item | Depends on |
|---|------|-----------|-----------|
| 01 | Packaging: boto3/psycopg in the base install, `local` stays an extra | 2 | — |
| 02 | Project and store descriptions: config, assistant context, New project and Project settings | 5 | — |
| 03 | Missing-descriptions popup | 5 (Q4) | 02 |
| 04 | Chat input: a box that grows | 6 | — |
| 05 | Chat: thinking indicator and tool-line spacing | 7, 8 | 04 |
| 06 | Seed assistant: prompt, `replace_seed`, `delete_seeds` | 9 | 02 |
| 07 | New project layout | 1 | 02 |
| 08 | Check store: one-line success | 4 | — |
| 09 | Search: centred first run, handoff results grids | 10 | 07 |
| 10 | Keep runs alive across navigation, RUNNING mark, upstream blocking | 11 (points 2–5) | — |
| 11 | Clickable rail | 11 (point 1) | 10 |
| 12 | Pointer styles | 3 | 11 |
| 13 | Docs | all | all |

Run strictly in order, one at a time (02 before 03, 06 and 07; 04 before 05; 10 before 11; 11 before 12). Needs a human: whether the mouse pointer changes in the terminals Chris uses, the glyph for RUNNING in those terminals, a real-model pass on the seed assistant, and a look at the finished Search results and the descriptions popup. Agents report these and stop; they never fake them.

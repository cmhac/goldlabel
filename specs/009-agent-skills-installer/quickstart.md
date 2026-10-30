# Quickstart: validating 009

All offline; no real agent, key or database. Run from the repository root.

1. **Checks**: `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pytest`.
2. **Installer, per agent, in a scratch project and fake home** (also what `tests/test_cli.py` does):

   ```bash
   mkdir -p "$SCRATCH/proj" "$SCRATCH/home" && cd "$SCRATCH/proj"
   HOME="$SCRATCH/home" uv run --project /home/user/goldlabel goldlabel install all --dry-run
   HOME="$SCRATCH/home" uv run --project /home/user/goldlabel goldlabel install claude codex copilot kiro
   HOME="$SCRATCH/home" uv run --project /home/user/goldlabel goldlabel install claude codex copilot kiro   # all "up to date"
   ```

   Expect `.claude/skills`, `.agents/skills` (once), `.kiro/skills` and `.kiro/steering/goldlabel.md`
   with seven skill folders each; the second run writes nothing; editing an installed `SKILL.md` then
   re-running exits 1 until `--force`.
3. **From the wheel**: `uv build`, list the wheel (`goldlabel/skills/*/SKILL.md`, `goldlabel/cli.py`,
   the `goldlabel` console script in `entry_points.txt`), install it in a clean venv without the
   checkout and run `goldlabel install claude --dir "$SCRATCH/out"`.
4. **Plugin manifest**: `claude plugin validate .` still passes with `"skills": ["./src/goldlabel/skills"]`
   (the sandbox has the `claude` CLI; if it cannot run offline this is reported as unchecked).
5. **Fold**: the end-to-end test labels dev and test rows over HTTP with a stub model, evaluates the
   test split, calls `gold.fold_test()`, and checks only `split` changed, `eval_log()` shows the fold
   and a count of zero test evaluations, a fresh `draw(split="test")` is pending, and a second
   `fold_test()` and one with a pending test row both raise `GoldError`.
6. **Needs a human** (report, never fake): each agent really lists the skills after install (Codex
   `$`, Copilot `/skills reload`, Kiro default agent and a custom agent with the `resources` line,
   Claude Code `/goldlabel:...` and plain skill names), and the gold-rule refusal trial in each.

## Results (2026-10-30, T014)

- Checks: ruff, ruff format, ty clean; `uv run pytest`: 621 passed, 18 skipped (the Postgres integration tests need `GOLDLABEL_TEST_PG_URL`; one Parquet test needs `pyarrow`).
- Step 2: in a scratch project and home, `goldlabel install claude codex copilot kiro` wrote 22 items (7 skill folders in each of `.claude/skills`, `.agents/skills` once, `.kiro/skills`, plus `.kiro/steering/goldlabel.md`); the second run reported every line "up to date"; an edited `SKILL.md` exited 1 with "differs (use --force to replace)".
- Step 3: wheel built and installed in a clean venv without the checkout; `goldlabel install --dir` worked (see the T006 commit).
- Step 4: `claude plugin validate .` passes with `"skills": ["./src/goldlabel/skills"]`.
- Step 5: `tests/test_e2e.py::test_a_spent_test_split_is_folded_and_a_fresh_one_is_labelled_by_people`.
- Step 6: not run (needs a person in each agent).

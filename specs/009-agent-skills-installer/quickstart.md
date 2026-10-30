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

# 13 — Docs

Spec: all items. Depends on every other task.

**Do**
- `README.md`: Install (`uv tool install hunches`, `hunches[local]` for local embeddings: large, unavailable on Python 3.14), New project (about panel and why both descriptions are required, the popup for older projects, Check store's one-line result and Details), Brief (the assistant asks questions first, writes corpus-voiced seeds, can replace and delete seeds), navigation (click the rail; runs keep going when you move around; Stop is the only way to stop one; changing project asks first; the RUNNING mark), chat (the box grows; `ctrl+j` for a newline), pointer note (needs a terminal that supports it).
- `AGENTS.md`: Current state (006 implemented, tasks 01–13; what still needs a human), source-of-truth list (add `specs/006-test-run-fixes/spec.md`, "Verified in task NN" notes win over the draft text), Stack (`local` extra only), Commands (`uv sync --extra local`), Layout (`screens/descriptions.py`; `Config.project_description/store_description`; `files.project_context/status_context`; `HunchesApp.kept/working/running_stages/upstream_running`; the rail is clickable), TUI look (the subhead class, the panel gap rule, `ChatInput`), Testing notes (the autouse `check_descriptions` stub and the `descriptions` marker).
- `specs/006-test-run-fixes/spec.md`: status line to "implemented (tasks 01–13)"; fold any "Verified in task NN" notes into place; note deviations.
- `specs/001-initial-version`, `002`, `003`, `005`: no rewrites. Add a one-line "changed by 006" pointer only where a statement there would now mislead a reader (the extras in 005's spec header, the 003 Search "dimmed before first run" line).

**Tests**: none new; run the full suite (`uv run pytest`), ruff and ty and report.

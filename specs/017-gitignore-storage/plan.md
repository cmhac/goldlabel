# Plan: 017 keep the cache and the lock file out of git

One helper, `ignore(folder, line)`, in `src/goldlabel/settings.py` (the module that already owns where files go): creates `folder/.gitignore` with `line`, or appends `line` when the file exists without it. No I/O at import.

- `cost.py`: `cache_put` and `_write` already `mkdir` the cache directory; each then calls `ignore(directory, "*")`. (Both sites are the only ones that create it.)
- `_label.py`: `_acquire` calls `ignore(lock.parent, lock.name)` after the mkdir.
- Tests (`tests/test_settings.py`, `test_cost.py`, `test_label_server.py` as fits): hand-written expected content; `git check-ignore` on a `git init` tmp repo proves FR in scenario 5.
- Docs: one sentence in the README storage section if it lists the folder contents; AGENTS.md current-state line.

Constitution check: no new dependency, no git run by the library (the test runs git, the library only writes a file), the gold rule untouched, ponytail: smallest change, one helper, two call sites.

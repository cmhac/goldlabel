# Feature Specification: Keep the cache and the lock file out of git

**Created**: 2026-11-09 · **Status**: Implemented · **Closes**: issue #17 (title, and the comment "should also ignore the lock file")

## Where things are today

The storage folder (`.goldlabel/` by default) holds files worth committing (`gold*.json`, `evals.jsonl`, `candidates.jsonl`) next to files that are not: `cache/` (one JSON file per model answer, plus the cost ledger `cost.json`) and `labelling.lock` (a pid, a port and a start time of one running server). Nothing ignores them, so `git status` shows hundreds of cache files and a lock file that is stale on any other machine.

## User story (P1)

As someone who commits their notebook and `.goldlabel/` to git, I never see the cache or the lock file in `git status`, and I do not have to write a `.gitignore` myself.

### Acceptance scenarios

1. **Given** the library creates a cache directory (any location: the default, a path the caller passed), **Then** that directory holds a `.gitignore` whose content is `*`, so everything in it, the ledger included, is ignored, and the `.gitignore` itself with it.
2. **Given** a labelling server takes the lock in a storage folder, **Then** the folder holds a `.gitignore` that ignores `labelling.lock`.
3. **Given** the folder already has a `.gitignore` (the user's own), **Then** it is never overwritten; a missing `labelling.lock` line is appended.
4. **Given** the cache is switched off (`cache=False`), **Then** nothing is written.
5. `git status` in a repo with a real `.goldlabel/` after a classify run and a labelling session lists no cache file and no lock file (checked with `git check-ignore` in a test).

## Requirements

- FR-001 The cache directory writes its own `.gitignore` (`*`) when the library first creates it. Rationale: the cache location can be anywhere the caller says, so the ignore travels with it; nothing is written into a folder the library does not own.
- FR-002 `_acquire` in `_label.py` makes sure `<folder>/.gitignore` has a `labelling.lock` line.
- FR-003 Existing content is kept; the write is idempotent.
- FR-004 Gold, evaluation and candidate files are **not** ignored: they are the record.

## Deliberately skipped

- A `goldlabel` command or option to turn this off (nobody asked).
- Ignoring an existing cache directory created before this change (it gets the file on the next write; a user can delete the cache any time).
- Touching the repo's own `.gitignore` or any file outside the storage folder.
- The gold rule is untouched.

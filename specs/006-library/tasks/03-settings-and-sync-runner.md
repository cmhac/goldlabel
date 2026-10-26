# 03 — Settings, locations and the sync/async runner

Spec: "Where files go", "Notebooks and scripts" (sync wrappers), FR-1, FR-3, FR-10 (first part).

**Do**
- `src/hunches/settings.py`: a module-level object `settings` with `root` (a `pathlib.Path`). Initial value: `HUNCHES_DIR` if set, else `.hunches`. Assigning changes it for the process; it is read at call time, never cached at import. One helper `resolve(path, default_name)` implementing "a path argument beats the setting beats the default": `path` if given, else `settings.root / default_name`. No directory is created by reading; writers create their own parents when they write.
- `src/hunches/_sync.py`: `run(coro)`: `asyncio.run(coro)` when no event loop is running in this thread; when one is, run the coroutine to completion on a worker thread with its own event loop and return its result or re-raise its exception. No `nest_asyncio`. A second call must work after the first (nothing reused across loops). `KeyboardInterrupt` in the calling thread cancels the worker's tasks and joins it; if that cannot be made reliable, write down what was found in the spec's "Notebooks and scripts" section.
- A `tests/conftest.py` autouse fixture that resets `settings.root` and deletes `HUNCHES_DIR` for every test.

**Tests (red first)**: default root; `HUNCHES_DIR` sets the initial value (re-import in a subprocess or reload the module); assignment changes where `resolve` points on the next call; explicit path beats setting beats default; `run` returns a value and re-raises an exception from outside a loop; the same inside a running loop (an `async def` test calls the sync function); two calls in a row inside a loop; a coroutine that itself uses `asyncio.sleep` and `asyncio.gather` works on the worker; importing `hunches.settings` writes nothing and reads no environment except `HUNCHES_DIR` (FR-1).

**Not in this task**: using these anywhere else; later tasks adopt them.

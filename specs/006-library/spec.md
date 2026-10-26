# 006 — Library, not TUI

Status: **draft for Chris's review** (2026-10-26). Supersedes the interface of 001–005: the Textual TUI, projects, system settings, stage tracking and history are removed; the search, classifier, metrics and cost logic they were built on are kept and re-exposed as a Python library. Where this spec and 001–005 disagree about anything user-facing, this spec wins. Behaviour of the kept logic (similarity floor, bands, cache key, metrics definitions, pgvector read-only rules) is **unchanged** unless said otherwise.

**Read order for an implementer:** this spec, then `tasks/` (to be written once the open questions at the end are answered), then the 001–005 sections named under "What is kept".

## What this is, in one paragraph

`hunches` becomes a Python library for content analysis over an already-embedded corpus: seed phrases → semantic search → candidates → an LLM classifier validated against a hand-labelled gold set → classified output. There is no application, no console script and no tracked status. A person builds the analysis **step by step in a Jupyter notebook** (or a script), alone or with a coding agent (Claude Code, Codex, GitHub Copilot, Kiro), by chaining plain function calls whose results display themselves in the notebook. The one thing that needs a real UI, building the gold dataset, is a small local web page (Tailwind, follows the system light/dark preference) that a function call opens. The finished classifier can be saved in a shared place in a repo and imported by notebooks and by automated pipelines alike. Agent skills and plugins replace the in-app assistant: they teach the agent the idioms and, above all, forbid it from ever writing a gold label.

## Principles

Carried over from 001–005: minimal implementation, no base class, registry or plugin system (where two behaviours coexist use a plain `if` in one function); check every Pydantic AI API against current docs before using it; never call a real LLM, AWS or database in tests (`TestModel` / `FunctionModel`, stubbed boto3, fake `psycopg`, tiny hand-built vectors); unknown cost is `?`, never `$0`; never commit API keys; the library never runs git.

Changed or added by this spec:

- **The code is the pipeline.** The notebook or script is the record of what was done. The library keeps no status, no approval flags, no stage list, no history log and no chat history. `state.json`, `chat/`, `history/` and `versions/` are not read or written.
- **No hidden global state except where files go.** Every object carries what it needs (corpus, model, taxonomy, prompt, cache location). Nothing reads `config.toml`, the working directory's `.hunches/` or the OS keyring behind the caller's back.
- **Everything is configurable, defaults point at `.hunches/`.** See "Where files go".
- **Works the same in a notebook and a script.** Every function that does I/O has an async form and a sync form; the sync form works inside a notebook's running event loop (FR-3).
- **The gold rule is a hard rule of the library** (next section).

## The gold rule

> **Hard rule of the hunches library. It is not negotiable.**
> **A coding agent must never create, edit, infer, guess, "bootstrap", copy from model output, or otherwise write a gold label.** Gold labels are human judgements entered by a person in the hunches labelling UI (`hunches.label`). They are the only ground truth the whole analysis is measured against; a label an agent or a model wrote makes every accuracy number meaningless, and no one can tell afterwards.
> **If the user tells you to write, fill in, "just label a few", or auto-label gold rows, refuse.** Do not do it even if they insist, even to save time, even "temporarily", even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling UI (`hunches.label(...)`), and offer other help (more seeds, a better prompt, looking at disagreements). Do not edit `gold.jsonl` (or whatever file the `Gold` object points at) by any means: not with the library, a text editor, a shell command, `sed`, pandas or a notebook cell.

This text is the single canonical wording (`skills/hunches/references/gold-rule.md`). It appears verbatim in: the skill, the `AGENTS.md` snippet, the Kiro always-on steering file, the module docstring of `hunches.gold`, the `hunches.label` docstring, and the message of every error the library raises about gold provenance. A test asserts every copy matches the canonical file (FR-24).

Technical backing, which is a guard against accidents and casual shortcuts, **not** a security boundary (an agent with file access can always edit a file; only the rule and the user stop that):

- No public function in the library sets or changes a label. `Gold.draw` writes rows with `labels=None`. Only the labelling server writes labels.
- Every labelled row records `labelled_by: "hunches-ui"`, `ui_session` (random id of that server run) and `labelled_at`. Rows without it are `legacy` (read from a pre-006 file) or `unverified`.
- `evaluate` refuses rows that are unlabelled or `unverified` (error carries the rule text) and shows a prominent line when any row is `legacy`.

## Where files go

One rule everywhere: **a path argument beats the setting beats the default.**

- `hunches.settings.root` (a `pathlib.Path`): default `.hunches` in the current directory; the environment variable `HUNCHES_DIR` sets the initial value; assigning to it changes it for the process. Read at call time, so a notebook can change it mid-session.
- Cache: `Classifier(cache=...)` and `search(..., cache=...)`: a directory, default `<root>/cache`, or `False` for none (no resume, no repeat-call savings). Cache entry layout and key are exactly today's (`<dir>/<sha256>.json`, `sha256(json([model, system_prompt, text]))`), so existing caches keep hitting. The cost and timing ledger is one file inside the cache directory.
- Artifacts: each function that produces one takes `out=` (`path`, or `False` to keep it in memory only). Defaults, because a notebook build-out should leave files behind: `search` → `<root>/candidates.jsonl` (with `.meta.json` beside it), `Gold()` → `<root>/gold.jsonl`. `Classifier.classify` writes only when `out=` is given (an automated pipeline must name its output). `evaluate` and `band_sample` return values; their results have `.write(path)`.
- Inputs are always explicit paths or objects: `read_seeds("seeds.csv")`, `Taxonomy.read("taxonomy.yaml")`, `Candidates.read("candidates.jsonl")`.

## The pieces

Names are proposals; shapes are the requirement. Everything below lives in the top-level `hunches` namespace. All result objects have a useful `repr()` for scripts and a `_repr_html_()` for notebooks (IPython's documented rich-display hook, [integrating docs](https://ipython.readthedocs.io/en/stable/config/integrating.html)). Tables expose `.rows` (a list of dicts); `.to_pandas()` imports pandas lazily and says how to install it if missing.

```python
import hunches as hn

corpus = hn.PgCorpus(url_env="HUNCHES_PG_URL", table="posts", text_column="body")   # or S3Corpus, LocalCorpus
seeds = hn.read_seeds("seeds.csv")                       # or a plain list[str]
candidates = hn.search(corpus, seeds, embedder="openai:text-embedding-3-small")     # Candidates; cached

taxonomy = hn.Taxonomy(mode="multi", labels={"scam": "Offers a fake prize...", "satire": "..."})
clf = hn.Classifier("anthropic:claude-haiku-5-5", taxonomy, prompt=open("prompt.md").read())

gold = hn.Gold()                                         # <root>/gold.jsonl
gold.draw(candidates, n=50, split="dev")                 # pending rows, no labels
hn.label(gold, taxonomy)                                 # opens the web page; returns when the human is done

ev = hn.evaluate(clf, gold.dev)                          # Evaluation: metrics + disagreements
# ... agent and user read ev.disagreements, edit the prompt, build a new Classifier, evaluate again

gold.draw(candidates, n=50, split="test"); hn.label(gold, taxonomy)
final = hn.evaluate(clf, gold.test)

report = hn.band_sample(clf, candidates, per_band=30)    # BandReport: off-topic rate per band
est = clf.estimate(candidates.above(0.70))               # Estimate: calls, $ or ?, time
results = clf.classify(candidates.above(0.70), out="results.jsonl", max_cost=1.5 * est.dollars)

clf.save("classifiers/scams/", evaluation=final)         # shared location in a repo
```

### Corpus (`LocalCorpus`, `S3Corpus`, `PgCorpus`)

Three small dataclasses, no base class. Fields are today's `Config` backend fields (`corpus_dir`; `s3_bucket`, `s3_index`, `s3_region`; the `pg_*` fields with the same names minus the prefix and the same defaults, including `search="exact"|"index"`, `auth="url"|"rds_iam"`, the two-table layout and `statement_timeout_s`). `search()` dispatches with a plain `if`/`match` on the class. The database URL is never a field: `PgCorpus` takes `url_env` (name of the environment variable, default `HUNCHES_PG_URL`); the library never reads or writes the OS keyring. `corpus.check()` is today's `check_store`. All pgvector rules of 005 and its deltas hold (read-only, `psycopg.sql.Identifier`, the `NaN` guard, the 512 MB result limit becomes `PgCorpus(max_result_mb=512)`).

### `search(corpus, seeds, *, embedder, floor=0.60, out=None, cache=None) -> Candidates`

Same behaviour as `candidates.build_candidates`: embed seeds, search, an item's score is its maximum similarity across seeds, ties go to the earlier seed. `embedder` is a model string (`"openai:text-embedding-3-small"`) or a pydantic-ai `Embedder`; an embedding-model mismatch between a local corpus's `meta.json` and `embedder` raises. Seed embeddings are cached (key: model + text) so re-running with one changed seed re-embeds one seed; the search itself is re-run (it is the corpus's cost, not the LLM's).

`Candidates`: `.rows`, `.capped` (true when a backend cap may have hidden hits; the repr shows a warning), `.floor`, `.above(t)` (a new `Candidates`), `.bands()` (counts per 001 band), `.sample(n, seed=None, exclude=())` (without replacement), `.top_seeds(threshold)`, `.read(path)` / `.write(path)`. HTML repr: count, per-band bars, and the warning. Bars use `currentColor`/opacity, never a hard-coded background.

### `Taxonomy`

Today's model (`mode: single|multi`, labels with descriptions, `off_topic` built in and exclusive) plus `Taxonomy(mode=..., labels={"name": "description"})`, `.read(path)`, `.write(path)`, `.labels` including `off_topic`. HTML repr: a table of labels and descriptions.

### `Classifier`

`Classifier(model, taxonomy, prompt, *, cache=None)`. Immutable: `clf.with_prompt(text)` and `clf.with_taxonomy(t)` return new ones, so a notebook can hold `clf_v1`, `clf_v2` side by side. `clf.digest` is today's `run_digest` (model + system prompt); results rows carry it as `run`.

- `clf.classify(items, *, out=None, max_cost=None, concurrency=8, progress=...) -> Predictions` and `await clf.aclassify(...)`. `items` is a list of `str` (id = position) or of dicts / rows with `id` and `text`, or any result object with `.rows`.
- Per-item failures (validation retries exhausted, model errors) are recorded on the prediction (`error`), never raised and never cached, exactly as today.
- With `out=`: rows `{id, text, labels, reasoning?, run, ...input fields}` are appended as each completes; ids already present in `out` with a successful row under the same `run` are skipped (resume). A row under a different `run` is re-classified.
- `max_cost`: raise `CostLimit` before starting if the estimate exceeds it; stop (resumably) mid-run if live spend crosses it. If the price of the model is unknown and `max_cost` is set, refuse (it cannot be honoured); never treat unknown as zero.
- `clf.estimate(items) -> Estimate`: `n`, `cached`, `live`, `dollars` (float or `None`), `seconds` (float or `None`), from the cache and the recorded sample usage/timing, as in 001 stage 8. Repr shows `cost ?` plus a warning when unknown. Calls no model.
- `clf.save(dir, evaluation=None)` / `Classifier.load(dir)`: a bundle folder `classifier.yaml` (model), `taxonomy.yaml`, `prompt.md`, optional `evaluation.json` (the final metrics, n, date, `digest`). `load` warns if the bundle's digest no longer matches its recorded evaluation. The cache location is **not** part of the bundle (it is runtime); `load(dir, cache=...)`.
- A classifier can equally be declared in code in a shared module (`classifier = hn.Classifier(...)`) and imported. Both forms are supported and documented.
- HTML repr: model, labels, a short prompt preview, digest, and the recorded evaluation if any.

### `Gold`, `GoldSet`, `label`

- `Gold(path=None)` loads or creates the file (default `<root>/gold.jsonl`). Row: `id, text, labels, split ("dev"|"test"), labelled_by, ui_session, labelled_at` (`labels` is `null` while pending).
- `gold.draw(candidates, n=50, split="dev", seed=None)`: appends `n` pending rows sampled without replacement from candidates not already anywhere in gold (so dev and test stay disjoint). Never writes labels.
- `gold.dev`, `gold.test`, `gold.pending`: `GoldSet` views of the file. `GoldSet.counts(taxonomy)` (per-label counts, so under-represented labels are visible), `.rows`, HTML repr.
- `gold.orphaned(taxonomy)`: rows whose labels are no longer in the taxonomy. `gold.remove(ids)` moves rows to `<gold>.removed.jsonl` (never deletes); this is a destructive act the agent must ask the user about.
- `hn.label(gold, taxonomy, *, split=None, block=True, open_browser=True, port=None)`: starts the labelling server (below) on `127.0.0.1`, prints the URL, opens the browser, and (by default) returns when the person presses **Done**. With `block=False` it returns a handle with `.url`, `.wait()` and `.stop()`. A second server on the same file is refused (lock file).

### `evaluate(clf, gold_set, *, metric=None, target=None) -> Evaluation`

Classifies the labelled rows (cached) and computes today's `compute_metrics` unchanged: exact-match accuracy, per-label precision/recall/F1, macro-F1, micro-F1, with `off_topic` a label like any other. `metric` defaults per mode as today (`accuracy` for `single`, `macro_f1` for `multi`); `target` adds PASS/FAIL beside the number (never colour alone). `Evaluation`: `.metrics`, `.score(name)`, `.disagreements` (rows with `id, text, gold, predicted, reasoning`), `.digest`, `.n`, `.write(path)`, HTML repr with the metrics table, per-label table and a browsable disagreement list. Refuses unlabelled or `unverified` rows (see the gold rule). Each evaluation of the **test** split appends one line (`digest`, metrics, time) to `<gold>.test_evals.jsonl`; the Evaluation repr shows "test split evaluated N times (M distinct prompts)" so reuse of the test set is visible, not hidden.

### `band_sample(clf, candidates, *, per_band=30, seed=None) -> BandReport`

Classifies ~`per_band` random items per similarity band; reports the off-topic rate per band (off-topic = predicted label set exactly `{off_topic}`) and the cost. The cutoff is chosen by a person and passed as a plain float to `candidates.above(t)`. No persisted `threshold.json`.

### Cost

`hn.cost(cache=None)` returns the running total and per-model breakdown from the ledger in the cache directory; any unknown price makes the total `?` with a warning. Classification and embedding calls record to it; cache hits record nothing.

## The labelling web page

Started only by `hn.label`. Requirements:

- **Stack:** Python standard library HTTP server (`ThreadingHTTPServer`), one HTML page, vanilla JavaScript, no build step for users and no new runtime dependency. Styling is Tailwind: a pre-built `app.css` is generated at release time with the Tailwind standalone CLI from the page's classes and committed under `src/hunches/web/`; the Play CDN is not used (it needs network access and is meant for development). The CSS is served by the local server, so the page works offline.
- **Dark mode (hard requirement):** follows the system preference with no toggle needed. Tailwind's `dark:` variant uses the `prefers-color-scheme` media query by default ([Tailwind docs](https://tailwindcss.com/docs/dark-mode)), so the page uses the default variant and also sets `<meta name="color-scheme" content="light dark">` so native controls and scrollbars match. Contrast meets WCAG AA in both schemes.
- **Security:** binds `127.0.0.1` only, random port by default, a per-run token in the URL required on every request, no external requests, no cookies.
- **Behaviour:** shows one item at a time with the taxonomy's labels and their descriptions; `single` mode is one choice, `multi` allows several, `off_topic` is exclusive; number keys choose labels, Enter/→ advances, ← goes back and a previous label can be changed; Skip; progress ("17 / 50"); a live per-label count table; every action is saved to the gold file immediately (atomic write), so closing the tab loses nothing and re-running `hn.label` resumes at the first unlabelled row. **The classifier's prediction is never shown** to the person (anchoring).
- **Layout:** usable at 360 px wide and up; no horizontal page scroll.
- A finished split (all rows labelled) shows a summary and the **Done** button.

## Notebooks and scripts

- **Sync wrappers (FR-3):** each `x` has an `ax`. `x` uses `asyncio.run` when no loop is running; when one is (Jupyter, Colab, marimo) it runs the coroutine to completion on a worker thread with its own event loop. `nest_asyncio` is not used (its repository is archived, [GitHub](https://github.com/erdewit/nest_asyncio/)). Agents are built per call, never reused across loops, which avoids the "Event loop is closed" failure described in the [Pydantic AI troubleshooting page](https://ai.pydantic.dev/troubleshooting).
- **Progress:** long calls print a single updating line (done/total, live vs cached, running cost) in a terminal and a notebook; `progress=False` silences it; `progress=callable` receives `(done, total, info)`.
- **Restarting the kernel loses nothing:** artifacts are files and API calls are cached, so re-running the notebook top to bottom is cheap and reproduces the same state.
- **Automated use:** `Classifier.load(...)` or an import, then `clf.classify(new_items, out=...)`. No gold, no UI, no network except the model provider (and the corpus, if searching).

## Agent integration

The skills are the replacement for the in-app assistant. They contain **guidance, not a state machine**.

- `skills/hunches/SKILL.md` (frontmatter `name: hunches`, a `description` that triggers on content analysis / classifying a corpus / gold labels) and `skills/hunches/references/`: `gold-rule.md` (canonical), `workflow.md` (the idiom above and what to ask the user at each point: the brief, which seeds are true of a match, single vs multi label, what makes a good label description), `tuning.md` (read `ev.disagreements`, change one thing, re-evaluate, stop at the target; never tune on the test split), `running.md` (estimate, show cost, ask, `max_cost`), `reuse.md` (bundles, importing in a pipeline). Reference files load on demand.
- Hard rules in the skill besides the gold rule: never run the full classification without showing the estimate and getting a yes; never evaluate the test split to guide edits; never put API keys or database URLs in a notebook, script or file (environment variables only); never edit a gold file.
- `AGENTS.md` snippet for projects whose agent has no skills (Copilot in the editor, others): the gold rule plus pointers.
- **Packaging per harness** (from the research in this session; each must be installed and exercised in the real harness before release, see "Needs a human"):
  - Claude Code and Codex: `.claude-plugin/marketplace.json` + `.claude-plugin/plugin.json`. Claude Code installs with `/plugin marketplace add owner/repo` and `/plugin install hunches@hunches`; Codex reads `.claude-plugin/marketplace.json` as a legacy marketplace location and installs with `codex plugin marketplace add owner/repo` then `codex plugin add hunches@hunches` ([Claude Code](https://code.claude.com/docs/en/plugins-reference), [Codex](https://developers.openai.com/plugins/build/plugins)).
  - Copilot CLI and Kiro: a root `plugin.json` per the Agent Plugins 1.0 spec (skills under `skills/`), which Copilot CLI documents ([GitHub](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-creating)) and Kiro Powers use ([Kiro](https://kiro.dev/docs/powers/)); Kiro also via `npx skills add <owner/repo> -a kiro-cli -g` ([Kiro skills](https://kiro.dev/docs/skills/)).
  - Kiro always-on rule: `.kiro/steering/hunches.md` carrying the gold rule (skills load only when relevant; the rule must always be present).
  - Any other agent: copy `AGENTS.md` or the skill folder.
- **No hooks in this version.** Hook formats differ per harness, Kiro cannot ship them in a package, and nothing here needs them. The gold rule's always-on presence comes from steering/`AGENTS.md`, not hooks.
- **Authoring notebooks with an agent:** agents differ in how well they edit `.ipynb` JSON. The skill tells the agent to build the pipeline as a plain script with `# %%` cell markers when it cannot edit notebooks natively, and tells the user they can convert it with jupytext. The library has no jupytext dependency.

## What is kept, changed, removed

| Kept (made library-shaped) | Source today |
|---|---|
| Vector search for local, S3 Vectors, pgvector (exact/index, IAM, two-table layout, scrubbing, `check_store`) | `search.py` |
| Candidate building, bands, floor | `candidates.py` |
| Classifier, validation, structured output, retries, cache | `classifier.py` |
| Metrics | `metrics.py` |
| Cost, cache, timing ledger, `genai-prices` | `cost.py`, `models.py` (price lookup only) |
| `Taxonomy`, `GoldRow` models | `files.py` |

Changed: functions take explicit arguments instead of reading `Config` and `Path(".hunches")` globally; `search.search` and friends take a corpus object; `cost` takes a cache directory; module-level `_MEMO` caches go.

Removed: `app.py`, `screens/`, `theme.py`, `hunches.tcss`, `history.py`, `keys.py`, `system.py`, the model pickers, `files.py`'s state/approval/staleness/versions/chat/pipeline-status code, the `hunches` console script, and the dependencies `textual`, `keyring`, `platformdirs`, `python-dotenv`, `pytest-textual-snapshot`. All TUI tests and the `ui` test marker go. Specs 001–005 stay in the repo as history, each marked superseded in its header.

Not read any more, left alone if present in an old project: `config.toml`, `state.json`, `brief.md`, `chat/`, `history/`, `versions/`, `threshold.json`, `test_result.json`. Still readable: `seeds.csv`, `candidates.jsonl`, `taxonomy.yaml`, `prompt.md`, `gold.jsonl` (rows without provenance are `legacy`), `results.jsonl`, `cache/`.

## Requirements

**Library**
- FR-1 Every function and class in "The pieces" works with explicit arguments only; importing `hunches` has no side effects (no files read or written, no network, no environment writes).
- FR-2 `import hunches` does not import `textual`, `keyring` or any module in the removed list.
- FR-3 Each I/O function has a sync and an async form; the sync form works when called from inside a running event loop (tested under a running loop, with a `FunctionModel`).
- FR-4 `Classifier` cache keys, `system_prompt` text and `run_digest` are byte-identical to today's; a test loads a cache entry written by the pre-006 code and gets a hit.
- FR-5 Search results equal today's for the same corpus, seeds and floor (local backend compared against numpy by hand-built vectors; pgvector against the existing fake-`psycopg` tests, ported).
- FR-6 Unknown prices show `?` everywhere a cost appears (reprs, progress line, `Estimate`, `cost()`), with a warning; `max_cost` with an unknown price refuses.
- FR-7 `classify(out=...)` is resumable and idempotent: killing it mid-run and re-running classifies only the missing ids and only the missing ones are live calls.
- FR-8 Per-item failures are returned, not raised, and never cached.
- FR-9 `Classifier` and the corpus classes are immutable value objects (frozen dataclasses); `with_prompt`/`with_taxonomy` return new ones, so no cell can change another cell's classifier.

**Locations**
- FR-10 `settings.root`, `HUNCHES_DIR`, `cache=`, `out=` behave as in "Where files go"; a test sets each and checks where files land; `cache=False` writes nothing.
- FR-11 No function writes outside the paths it was given or the configured root.

**Notebook display**
- FR-12 `Candidates`, `Taxonomy`, `Classifier`, `Predictions`, `Gold`/`GoldSet`, `Evaluation`, `Estimate`, `BandReport` define `__repr__` and `_repr_html_`; the HTML escapes all item text, sets no foreground or background colour (inherits from the notebook theme) and conveys state with words as well as colour (PASS/FAIL, `?`, WARNING).
- FR-13 Reprs of large objects are bounded (a row cap with a "N more" line).

**Gold and the labelling page**
- FR-14 No public API sets or edits a label; `Gold.draw` writes `labels=None`; only the server writes labels and stamps provenance.
- FR-15 `evaluate` refuses unlabelled/`unverified` rows with the gold-rule message and flags `legacy` rows in its repr.
- FR-16 `draw` never returns an id already in the gold file; dev and test are disjoint.
- FR-17 The server meets every item in "The labelling web page": local-only, tokened, offline, autosave, resume, no prediction shown, `single`/`multi`/`off_topic` rules identical to `files.validate_labels`.
- FR-18 The page follows `prefers-color-scheme` in both directions (tested by emulating both schemes in a headless browser; an HTTP-level test covers the API and validation).
- FR-19 A second `label` on the same gold file is refused while the first runs; a crashed server's stale lock is detected and replaced.
- FR-20 The test-split ledger line is written on every test evaluation and shown in the repr.

**Reuse**
- FR-21 `save`/`load` round-trips a classifier; `load` warns when the digest differs from the recorded evaluation.
- FR-22 A script with no notebook, no gold file and no UI can `load` and `classify` (test it).

**Agent integration**
- FR-23 The skill, references, `AGENTS.md` snippet, Kiro steering file and plugin manifests exist and validate (`claude plugin validate` for the Claude/Codex manifest).
- FR-24 A test asserts the canonical gold-rule text appears verbatim in every location listed under "The gold rule" and in the provenance error message.
- FR-25 Docs: the README is rewritten around the notebook flow and the install commands for each harness; `AGENTS.md`/`CLAUDE.md` of this repo are updated (stack, commands, layout, principles) and no longer mention Textual.

## Success criteria

- SC-1 A scripted end-to-end test with `FunctionModel`/`TestModel`, tiny hand-built vectors and a simulated labelling session over HTTP runs the whole chain in the README example and passes, with zero real network calls.
- SC-2 A person who has never seen the TUI can reproduce the README example in a notebook, in order, with each cell's output explaining what happened and what to do next.
- SC-3 Re-evaluating the dev split with an unchanged prompt makes zero live calls; after a prompt change it makes exactly one live call per item and no more (checked by counting `FunctionModel` invocations).
- SC-4 Pre-006 caches and gold files from a real project are readable by the new code (checked by a fixture generated by the old code before it is removed).
- SC-5 Source size of `src/hunches` falls by at least half (it is 11,588 lines today); measured, reported in the final task.
- SC-6 In every location the agent will read, the gold rule is the same text, and a manual trial in each of the four target harnesses ends with the agent refusing a user instruction to label rows.

## Edge cases to cover in tests

Empty candidates; a capped search; `n` larger than available candidates in `draw`; taxonomy changed after labelling (orphans); two prompts evaluated back to back; kernel restart mid-run; `out=` file with rows from a different `run`; unknown model price; a pending gold row in `evaluate`; a gold file hand-edited by a person (shows as `unverified`, with the message explaining how to relabel it in the UI); a browser tab closed mid-label; a port already in use.

## Out of scope

A CLI; MCP server; hooks; a persisted status or approval system; undo/redo (use git); web pages for thresholds, results browsing or settings (notebook reprs cover them); multi-annotator labelling and agreement scores; hosting the labelling page for remote people; embedding the corpus; writing to the corpus; a keyring or any key storage.

## Open questions for Chris

1. **[NEEDS CLARIFICATION] Remove the TUI in this branch?** Recommendation: yes, in the last task of 006, since `v0.1.0` has not been tagged or published (so no released version loses it) and keeping both doubles the maintenance this spec exists to remove. The old code stays in git history.
2. **[NEEDS CLARIFICATION] Importing existing human-labelled gold** (e.g. a spreadsheet labelled elsewhere). Recommendation: no importer; a person who wants this can place a file by hand, rows then show as `unverified` and `evaluate` refuses them until relabelled in the UI, or the person accepts `legacy` treatment. An importer is exactly the tool an agent would misuse.
3. **[NEEDS CLARIFICATION] Test-split ledger** (`.test_evals.jsonl`, FR-20). Recommendation: keep; it is a log, not status, and it makes test-set reuse visible. Drop it if you read it as tracking.
4. **[NEEDS CLARIFICATION] Headless browser in CI** for FR-18. Recommendation: add Playwright as a dev dependency and run the dark/light test in CI only. Alternative: assert only that the served CSS contains the `prefers-color-scheme` rules and the meta tag.
5. **[NEEDS CLARIFICATION] Where the gold rule's canonical text lives.** Recommendation: `skills/hunches/references/gold-rule.md`, copied into the package data at build time so `hunches.gold` can show it at runtime and the consistency test (FR-24) has one source.

## Needs a human (stop and report, don't fake)

Installing and exercising the plugin in each of Claude Code, Codex, Copilot CLI and Kiro (the Codex hook trust step does not apply because there are no hooks; check that Codex really picks up `.claude-plugin/marketplace.json`, and that Copilot CLI's marketplace lookup accepts the repo), the gold-rule refusal trial in each (SC-6), a real browser check of the labelling page in light and dark on at least one desktop and one phone-width viewport, a real notebook run in Jupyter and one other notebook (marimo or Colab), and everything 005 already lists (a real pgvector/RDS/S3 corpus, API keys).

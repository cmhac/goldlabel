# 006 — Library, not TUI

Status: **approved by Chris 2026-10-26** (decisions at the end); tasks in `tasks/`. Supersedes the interface of 001–005: the Textual TUI, projects, system settings, stage tracking and history are removed; the search, classifier, metrics and cost logic they were built on are kept and re-exposed as a Python library. Where this spec and 001–005 disagree about anything user-facing, this spec wins. Behaviour of the kept logic (similarity floor, bands, cache key, metrics definitions, pgvector read-only rules) is **unchanged** unless said otherwise.

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
- **The gold rule is a hard rule of the library, enforced by instructions to agents only** (next section). The library does not restrict users; they are responsible, honest and transparent about their data.

## The gold rule

Integrity of the pipeline is protected by **instructions to the agent and nothing else**. The library does not restrict people: how a user obtains their gold labels, and what they report about them, is their responsibility, to be honest and transparent. What the library does is make the rule impossible for an agent to miss and make provenance visible (below).

The canonical text lives in **`src/hunches/gold_rule.md`** (package data, so the library can print it at run time). It has two forms, `## Short` and `## Full`, reproduced here.

**Short** (one sentence; goes wherever space is tight, including skill descriptions):

> **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`hunches.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**

**Full:**

> **Hard rule of the hunches library. It is not negotiable.**
> **Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the hunches labelling page (`hunches.label`), or bring a dataset that people have already labelled.
> **If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
> Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

### Where the rule reaches the agent without a tool call or any action by it

The requirement is that the rule is already in the agent's context, not something it has to go and fetch. Channels, from most to least universal:

| Channel | How it gets into context | Form |
|---|---|---|
| `description` in the skill's frontmatter | Skill names and descriptions are in context from the start of a session: Claude Code lists them in its context (visible in this session's own skill list), and Codex "starts with each skill's name, description, and file path" ([Codex skills](https://developers.openai.com/codex/skills)); Kiro and Copilot CLI match requests against it (to confirm in the trial, SC-6). Installing the plugin is the only user action. | Short |
| Project instruction file: `AGENTS.md` (Codex, Copilot CLI), `CLAUDE.md` (Claude Code), `.kiro/steering/hunches.md` with `inclusion: always` (Kiro) | Read at session start. The user pastes a block from the README once per project; the library offers it as `hunches.GOLD_RULE_FULL`. | Full |
| What the library prints when the agent runs code that touches gold: `repr(Gold)`/`repr(GoldSet)`, the return of `Gold.draw`, the text `hunches.label` prints, and the message of any error raised about gold | Cell and command output goes straight back to the agent. | Short |
| `SKILL.md` body | Loaded when the skill triggers. | Full |

A plugin is installed from the repo without the Python package, so the skill files hold literal copies of the text. A test (FR-24) fails when any copy drifts from `src/hunches/gold_rule.md`, printing the text to paste.

**Implemented in task 08** (`gold.py`; `files.GoldRow/read_gold/write_gold/orphaned_gold/gold_coverage` are gone with their tests): `GoldRow` allows extra keys, so a hand-edited file keeps them when the file is rewritten; `labelled_by`/`labelled_at` are written only when set. Every `Gold` view reads the file again (the labelling server writes it). A **pending** row is one with no labels: `labels: null` (written by `draw`) or `[]` (what pre-006 wrote); `gold.dev`/`gold.test` hold labelled rows only, `gold.pending` and `gold.all` are the other views, and each is a frozen `GoldSet(rows, name)`. `counts(taxonomy)` lists every name in `taxonomy.names` (zeros included) and ignores labels outside it (`orphaned` finds those). `repr`: `GoldSet dev: 4 rows (4 labelled, 0 pending); hunches-ui 1, imported 2, unstamped 1` (sources count labelled rows). `draw` and `import_rows` raise `ValueError` for a split other than `dev`/`test`; `draw` raises, writing nothing, when fewer than `n` candidates are outside the file (`only K candidates are not already in <path>; asked for N`); `import_rows` needs a non-empty `labels` list, refuses (writing nothing) an id already in the file or repeated in the batch. **`orphaned` changes meaning from 004**: it is the labelled rows with a label not in the taxonomy (this section), not rows missing from the candidates, and `gold_coverage` has no replacement. `remove(ids)` raises `ValueError` for an id not in the file (nothing changes) and `TypeError` for a bare string; the removed rows go to `<gold stem>.removed.jsonl` (e.g. `gold.removed.jsonl`) before the gold file is rewritten, so a crash cannot lose rows. Writes are a temp file `<name>.tmp` plus `os.replace`; on failure the temp file is deleted and the old file is intact. A malformed or invalid line raises `ValueError("<path>:<line>: not a gold row (...)")`. `tests/test_gold.py` pins the public names of `Gold` so a new mutator cannot be added unnoticed.

### What the library does and does not do about gold

- Does: `Gold.draw` writes pending rows (`labels=None`); the labelling page stamps the labels it writes with `labelled_by: "hunches-ui"` and `labelled_at`; imported rows are stamped `labelled_by: "imported"`; `Evaluation` and the evaluation log show how many rows came from each source (and how many have no stamp), so a reader of the notebook can see what the numbers rest on.
- Does not: refuse any gold file or any rows, require stamps, verify who labelled what, or try to stop a person (or an agent with file access) from editing a file. Those are choices for the user and the instructions to the agent.

## Where files go

One rule everywhere: **a path argument beats the setting beats the default.**

- `hunches.settings.root` (a `pathlib.Path`): default `.hunches` in the current directory; the environment variable `HUNCHES_DIR` sets the initial value; assigning to it changes it for the process. Read at call time, so a notebook can change it mid-session.
- Cache: `Classifier(cache=...)` and `search(..., cache=...)`: a directory, default `<root>/cache`, or `False` for none (no resume, no repeat-call savings). Cache entry layout and key are exactly today's (`<dir>/<sha256>.json`, `sha256(json([model, system_prompt, text]))`), so existing caches keep hitting. The cost and timing ledger is one file inside the cache directory.
- Artifacts: each function that produces one takes `out=` (`path`, or `False` to keep it in memory only). Defaults, because a notebook build-out should leave files behind: `search` → `<root>/candidates.jsonl` (with `.meta.json` beside it), `Gold()` → `<root>/gold.jsonl`. `Classifier.classify` writes only when `out=` is given (an automated pipeline must name its output). `evaluate` returns a value and appends one line to the evaluation log, default `<root>/evals.jsonl` (`log=` to move it, `log=False` to turn it off); `band_sample` returns a value. Result objects have `.write(path)`.
- Inputs are always explicit paths or objects: `read_seeds("seeds.csv")`, `Taxonomy.read("taxonomy.yaml")`, `Candidates.read("candidates.jsonl")`.

## The pieces

Names are proposals; shapes are the requirement. Everything below lives in the top-level `hunches` namespace. All result objects have a useful `repr()` for scripts and a `_repr_html_()` for notebooks (IPython's documented rich-display hook, [integrating docs](https://ipython.readthedocs.io/en/stable/config/integrating.html)). Tables expose `.rows` (a list of dicts); `.to_polars()` and `.to_pandas()` each import their library lazily and say how to install it if missing; both are always provided together (a hunches export function supports polars and pandas, never one alone). Where this spec, the docs or the example show tabular data in code, they use polars.

```python
import hunches as hn

corpus = hn.PgCorpus(
    url_env="HUNCHES_PG_URL", table="posts", text_column="body"
)  # or S3Corpus, LocalCorpus
seeds = hn.read_seeds("seeds.csv")  # or a plain list[str]
candidates = hn.search(
    corpus, seeds, embedder="openai:text-embedding-3-small"
)  # Candidates; cached

taxonomy = hn.Taxonomy(
    mode="multi", labels={"scam": "Offers a fake prize...", "satire": "..."}
)
clf = hn.Classifier(
    "anthropic:claude-haiku-5-5", taxonomy, prompt=open("prompt.md").read()
)

gold = hn.Gold()  # <root>/gold.jsonl
gold.draw(candidates, n=50, split="dev")  # pending rows, no labels
hn.label(gold, taxonomy)  # opens the web page; returns when the human is done

ev = hn.evaluate(clf, gold.dev)  # Evaluation: metrics + disagreements
# ... agent and user read ev.disagreements, edit the prompt, build a new Classifier, evaluate again

gold.draw(candidates, n=50, split="test")
hn.label(gold, taxonomy)
final = hn.evaluate(clf, gold.test)

report = hn.band_sample(
    clf, candidates, per_band=30
)  # BandReport: off-topic rate per band
est = clf.estimate(candidates.above(0.70))  # Estimate: calls, $ or ?, time
results = clf.classify(
    candidates.above(0.70), out="results.jsonl", max_cost=1.5 * est.dollars
)

clf.save("classifiers/scams/", evaluation=final)  # shared location in a repo
```

### Corpus (`LocalCorpus`, `S3Corpus`, `PgCorpus`)

Three small dataclasses, no base class. Fields are today's `Config` backend fields (`corpus_dir`; `s3_bucket`, `s3_index`, `s3_region`; the `pg_*` fields with the same names minus the prefix and the same defaults, including `search="exact"|"index"`, `auth="url"|"rds_iam"`, the two-table layout and `statement_timeout_s`). `search()` (task 06) calls `hunches.search.search_vectors(corpus, vector, floor, *, embedding_model)`, which dispatches with a plain `if` on the class and returns `(hits, capped)`; pgvector `exact` search for all seeds at once is `search_pg_exact(corpus, vectors, floor, progress=None, stop=None)`. The database URL is never a field: `PgCorpus` takes `url_env` (name of the environment variable, default `HUNCHES_PG_URL`) and the URL is read from that variable **only**; the library never reads or writes the OS keyring, and `pg_url_id`/`pg_url_name` (005 delta 02) are gone. `PgCorpus.check(seeds=None)` is today's `check_store` and exists **only on `PgCorpus`** (local and S3 have no check). Implemented in task 05 (`search.py`): the corpus classes are frozen dataclasses and `PgCorpus`/`S3Corpus` validate at construction (`table`/`url_env` non-empty, `search` in `exact|index`, `auth` in `url|rds_iam`, `max_result_mb` and `statement_timeout_s` not negative; `0` still means no limit); `statement_timeout_s` defaults to `None` (the server's own), as `pg_statement_timeout_s` did. Error and hint texts that named `config.toml`, `pg_*` fields, the keyring or System settings now name the `PgCorpus` field or the environment variable. All pgvector rules of 005 and its deltas hold (read-only, `psycopg.sql.Identifier`, the `NaN` guard, the 512 MB result limit becomes `PgCorpus(max_result_mb=512)`).

### `search(corpus, seeds, *, embedder, floor=0.60, out=None, cache=None) -> Candidates`

Same behaviour as `candidates.build_candidates`: embed seeds, search, an item's score is its maximum similarity across seeds, ties go to the earlier seed. `embedder` is a model string (`"openai:text-embedding-3-small"`) or a pydantic-ai `Embedder`; an embedding-model mismatch between a local corpus's `meta.json` and `embedder` raises. Seed embeddings are cached (key: model + text) so re-running with one changed seed re-embeds one seed; the search itself is re-run (it is the corpus's cost, not the LLM's).

`Candidates`: `.rows`, `.capped` (true when a backend cap may have hidden hits; the repr shows a warning), `.floor`, `.above(t)` (a new `Candidates`), `.bands()` (counts per 001 band), `.sample(n, seed=None, exclude=())` (without replacement), `.top_seeds(threshold)`, `.read(path)` / `.write(path)`. HTML repr: count, per-band bars, and the warning. Bars use `currentColor`/opacity, never a hard-coded background.

**Implemented in task 06** (`candidates.py`, `taxonomy.py`): `Candidates` is a frozen dataclass `(rows, capped=False, floor=0.60, seeds_digest=None, embedding_model=None)`; `.above(t)` and `.sample(n, seed=None, exclude=())` both return a new `Candidates` (`sample` returns all that remain when `n` is larger, and uses `random.Random(seed)`). `.write(path)` writes the rows and `<path stem>.meta.json` beside them with the old keys (`seeds_digest`, `written_at`, `floor`, `embedding_model`) plus `capped`; `.read(path)` takes the floor and `capped` from that file when it exists (an old meta has no `capped`: false; no meta: floor 0.60). `search` takes a `list[str]` (a bare `str` raises `TypeError`; `read_seeds(path)` reads a CSV) and has no `progress`/`stop` arguments; `seeds_changed` and `build_candidates` are gone, `seeds_digest` stays. Verified against pydantic-ai 2.53 and its embeddings docs: `Embedder(model)`, `await embedder.embed_query(text)` returns an `EmbeddingResult` (`.embeddings[0]`, `.usage`, `.cost()`), and `Embedder.model` is the string it was built with or an `EmbeddingModel` with `.model_name`. The model name used for the seed-embedding cache key and the local `meta.json` check is the string given as `embedder`, or `embedder.model` when that is a string, else `embedder.model.model_name` (so an `Embedder` built from a model object carries no `provider:` prefix and must match the corpus `meta.json` as is). Repr: `N candidates (floor 0.60)`, one `0.600-0.625  count` line per band, then the `WARNING: results were capped ...` line when `capped`.

### `Taxonomy`

Today's model (`mode: single|multi`, labels with descriptions, `off_topic` built in and exclusive) plus `Taxonomy(mode=..., labels={"name": "description"})`, `.read(path)`, `.write(path)`, `.labels` including `off_topic`. HTML repr: a table of labels and descriptions.

**Implemented in task 06:** `.labels` stays the list of labels you defined (`Label(name, description)`; it cannot include `off_topic` because `taxonomy.yaml` and the classifier prompt list only those), so "`.labels` including `off_topic`" is the property `.names` (`["a", "b", "off_topic"]`, same as `all_labels(taxonomy)`). `Taxonomy` is frozen; `labels` accepts a dict or a list of `Label`; `Taxonomy.read(path)` / `.write(path)` use the `taxonomy.yaml` format unchanged and `write` creates parent folders. `Taxonomy`, `Label`, `OFF_TOPIC`, `all_labels`, `validate_labels` live in `taxonomy.py`; `files.read_taxonomy/write_taxonomy` remain thin wrappers until task 11.

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

**Implemented in task 07** (`classifier.py`; `save`/`load` and the HTML repr are later tasks): `Classifier(model, taxonomy, prompt, *, cache=None)` is a frozen dataclass; `digest` is `sha256(json([model name, system_prompt]))`, byte-equal to the pre-006 `run_digest` (checked against the task-01 fixture), and the cache key and entry format are unchanged. `Predictions(rows, live, cached, resumed, cost)`: `rows` are in input order and hold `{id, text, labels, reasoning, run, ...other input fields}`; a failed item's row has `labels: None` and `error` instead of `reasoning`; `.errors` are those rows; `.labels` is the list of each row's labels (`None` for failures); `resumed` counts items already in `out` (their stored row is returned); `cost` is the live spend, `None` when any live price is unknown, never 0. `Estimate(n, cached, live, dollars, seconds)`: with no live calls both are `0.0`; otherwise `dollars` is `None` without a priced sample for the model (a first run, or `cache=False`) and `seconds` is `None` without recorded timing. Failed items are not written to `out`, so a resume retries them. Per-item failures that become error rows (FR-8) are `UnexpectedModelBehavior` (validation retries exhausted) and, added in a follow-up to task 07, pydantic-ai's `ModelAPIError` (its base class of `ModelHTTPError`; HTTP 429/5xx and other 4xx, timeouts and connection errors; checked against pydantic-ai 2.53), carried as `Prediction.api_error`. Not caught: programming errors, `CostLimit`, `KeyboardInterrupt` and `asyncio.CancelledError`. Two rules keep an outage from burning money: HTTP 401 and 403 (`FATAL_STATUSES`) are re-raised at once, because every remaining item would fail identically; and `MAX_API_ERRORS_IN_A_ROW = 5` API errors in a row (completion order; a live success or a validation failure resets the count, cache hits do not touch it) stop the run with a `ModelAPIError` ("stopped: 5 model API errors in a row; last: ..."). In both cases finished rows are already in `out`, so a re-run resumes, and error rows are never written to `out`, so a resume retries them. Other exceptions stop the run as before. `max_cost` raises `CostLimit` before starting when the live estimate is over it or unknown (a fully cached run needs no price), and mid-run when spend is strictly over it or a live call's price is unknown. `progress=True` prints one `\r`-updating line to stderr only on a terminal or in an ipykernel; callable gets `(done, total, info)` with `info` = `live`, `cached`, `errors`, `cost`. `is_cached`, the module-level `classify` and `classify_many` are gone (`system_prompt` and `Prediction` stay; `Prediction` gains `dollars`). `CostLimit` lives in `hunches.classifier` (public export in task 11).

### `Gold`, `GoldSet`, `label`

- `Gold(path=None)` loads or creates the file (default `<root>/gold.jsonl`). Row: `id, text, labels, split ("dev"|"test")` plus optional informational `labelled_by` (`"hunches-ui"`, `"imported"`, or absent) and `labelled_at`; `labels` is `null` while pending. Any file in this schema works, so an existing human-labelled dataset can be used by pointing `Gold` at it.
- `gold.import_rows(rows, split)`: adds already-labelled rows (dicts with `id`, `text`, `labels`) from a dataset people labelled elsewhere, stamping `labelled_by: "imported"`. Labels are validated against the taxonomy at `evaluate` time, so a mismatch is reported there (`gold.orphaned`), not refused here. The gold rule tells agents when this may be used.
- `gold.draw(candidates, n=50, split="dev", seed=None)`: appends `n` pending rows sampled without replacement from candidates not already anywhere in gold (so dev and test stay disjoint). Never writes labels.
- `gold.dev`, `gold.test`, `gold.pending`: `GoldSet` views of the file. `GoldSet.counts(taxonomy)` (per-label counts, so under-represented labels are visible), `.rows`, HTML repr.
- `gold.orphaned(taxonomy)`: rows whose labels are no longer in the taxonomy. `gold.remove(ids)` moves rows to `<gold>.removed.jsonl` (never deletes); this is a destructive act the agent must ask the user about.
- `hn.label(gold, taxonomy, *, split=None, block=True, open_browser=True, port=None)`: starts the labelling server (below) on `127.0.0.1`, prints the URL, opens the browser, and (by default) returns when the person presses **Done**. With `block=False` it returns a handle with `.url`, `.wait()` and `.stop()`. A second server on the same file is refused (lock file).

### `evaluate(clf, gold_set, *, metric=None, target=None, log=None) -> Evaluation`

Classifies the labelled rows (cached) and computes today's `compute_metrics` unchanged: exact-match accuracy, per-label precision/recall/F1, macro-F1, micro-F1, with `off_topic` a label like any other. `metric` defaults per mode as today (`accuracy` for `single`, `macro_f1` for `multi`); `target` adds PASS/FAIL beside the number (never colour alone). `Evaluation`: `.metrics`, `.score(name)`, `.disagreements` (rows with `id, text, gold, predicted, reasoning`), `.digest`, `.n`, `.write(path)`, HTML repr with the metrics table, per-label table and a browsable disagreement list. Pending (unlabelled) rows are skipped and counted in the repr. The repr also shows how many rows came from each source (`hunches-ui`, `imported`, unstamped). Nothing else is refused.

**Evaluation log.** Every `evaluate` call, for any split, appends one JSON line to the log (default `<root>/evals.jsonl`): `time`, `split`, `n`, `gold` (path), `model`, `digest`, `prompt` (the full text, so the history of the prompt is self-contained), `taxonomy` (mode and labels with descriptions), `metric`, `target`, `score`, the full `metrics` (overall and per label), `dollars` (`null` if unknown), `live_calls`, `cached_calls`, `hunches` version. The file is append-only and never rewritten. `hn.eval_log(path=None) -> EvalLog` reads it: `.rows`, a repr table (time, split, n, score, short digest, model) and a line such as "test split evaluated 3 times (2 distinct prompts)", so reuse of the test set is visible. Classification runs and band samples are not evaluations and are not logged here.

**Implemented in task 09** (`evaluation.py`; the public exports come in task 11, the HTML reprs in task 12): `evaluate` is `_sync.run(aevaluate(...))`. Gold rows whose labels fail `validate_labels` (unknown label, `off_topic` combined, wrong count for the mode) raise `ValueError` naming the ids and `gold.orphaned(taxonomy)`, before any model call and before anything is logged. An item whose classification failed has `predicted: None` and `reasoning: None` in `.disagreements` and counts as a prediction of no labels in the metrics. `.sources` counts labelled rows as `{"hunches-ui", "imported", "unstamped"}` (any other `labelled_by` value counts as unstamped). `target` is a minimum: PASS when `score >= target`; with no target the repr has no PASS/FAIL line. `Evaluation.write(path)` writes JSON (`time, n, skipped_pending, sources, digest, metric, target, score, metrics, disagreements`). To log the gold path, `GoldSet` gained an optional `path` field, set by the `Gold` views `dev/test/pending/all` (the sets `draw`, `import_rows`, `orphaned` and `remove` return have none, so their evaluation logs `gold: null`). `split` in the log is the rows' split, `"mixed"` when both occur, and the set's name when it has no labelled rows. The log line's `taxonomy` is `Taxonomy.model_dump()` (`mode` and `labels` as `{name, description}` list), `hunches` is the installed package version (`null` if not installed) and `dollars` is the live spend (`null` if any live price is unknown; `0.0` for a fully cached run). `eval_log` on a missing file has no rows. `band_sample` lists only bands that have candidates (candidates below the floor are ignored), `n` counts items that received labels (failed items are in `BandReport.errors`), every band is sampled with one `random.Random(seed)`, and all picked items go through one `clf.classify` call. `Metrics.from_dict` (unused since the TUI went) is deleted.

**Implemented in task 10** (`classifier.py`): `clf.save(dir, evaluation=None)` creates `dir` and writes `classifier.yaml` (`model: <name>` only; a `Model` object is saved by its `model_name`), `taxonomy.yaml`, `prompt.md` (newline-terminated) and, given an `Evaluation`, `evaluation.json` with `split`, `n`, `score`, `metric`, `metrics`, `digest`, `date` (UTC ISO) and `sources`. It touches no other file. `Classifier.load(dir, *, cache=None)` reads them back; `.evaluation` is the parsed dict (a plain attribute set by `load`, not a dataclass field, so `with_prompt`/`with_taxonomy` copies have none) or `None`, and one `UserWarning` is issued when its `digest` differs from the loaded classifier's. Spec gap fixed: `Evaluation` gained a `split` field (`dev`, `test` or `mixed`, the same value the evaluation log records) so the bundle can record it. A bundle stores the model as a string, so a test or script that wants a stub model swaps it with `dataclasses.replace(clf, model=...)`. A classifier declared in a shared module (`classifier = hn.Classifier(...)`) needs no code and is just imported.

### `band_sample(clf, candidates, *, per_band=30, seed=None) -> BandReport`

Classifies ~`per_band` random items per similarity band; reports the off-topic rate per band (off-topic = predicted label set exactly `{off_topic}`) and the cost. The cutoff is chosen by a person and passed as a plain float to `candidates.above(t)`. No persisted `threshold.json`.

### Cost

`hn.cost(cache=None)` returns the running total and per-model breakdown from the ledger in the cache directory; any unknown price makes the total `?` with a warning. Classification and embedding calls record to it; cache hits record nothing.

Implemented in task 04 (`cost.py`): every function takes `cache` first: a directory, `None` for the default `<settings.root>/cache`, or `False` for no cache (reads return nothing, writes do nothing). The ledger is `<cache>/cost.json`, written atomically (temp file + `os.replace`) under a process-wide lock, so threads lose no update; two *processes* sharing one cache directory can still lose a ledger update (cache entries are unaffected). A pre-006 `<root>/cost.json` is not read. `hn.cost` is the function `hunches.cost.cost`; its public export in `__init__` (task 11) shadows the submodule name `hunches.cost`, so code inside the package imports `from hunches.cost import ...` by name from then on.

**Implemented in task 11** (`__init__.py`, deletions): `files.py`, `system.py` and `models.py` are deleted with their tests (`keys.py` went in task 05). Nothing in `src/` used `models.py` (`price_label`, `snapshot_date`, `known_models` served only the model pickers and `cost` never called them), so it is deleted rather than trimmed, and the spec's "price lookup only" row no longer applies: `cost.py` prices through `genai-prices` directly. `keyring`, `platformdirs` and `python-dotenv` are no longer dependencies (`textual` was already gone); the library never loads `.env`. `hunches/__init__.py` exports exactly the names of "The pieces" plus `__version__` (package metadata; `0+unknown` if not installed); `label`, `GOLD_RULE_SHORT` and `GOLD_RULE_FULL` arrive in tasks 14 and 15. Importing is free of side effects, and `textual`, `keyring`, `platformdirs`, `dotenv`, `boto3` and `psycopg` are not imported by `import hunches`. **Name shadowing**: `hunches.search`, `hunches.cost` and `hunches.settings` are the function, the function and the object, not the submodules; always import by name (`from hunches.search import LocalCorpus`, `from hunches.settings import settings, resolve`), and a test that needs a whole module uses `importlib.import_module("hunches.cost")`. `uv run ty check` excludes `specs/` (the old design handoff imports `textual`).

**Implemented in task 12** (`_html.py`, `_frame.py`; methods on each class): `_repr_html_` exists on `Candidates`, `Taxonomy`, `Classifier`, `Predictions`, `Estimate`, `Gold`, `GoldSet`, `Evaluation`, `EvalLog`, `BandReport` and `Cost`; the plain `__repr__` outputs are unchanged (`Gold` still has none). All text goes through `html.escape`; the HTML sets no `color`, `background`, hex or `rgb`/`hsl` value (bars and rules use `currentColor` and `opacity`); state is also words (`PASS`/`FAIL`, `cost ?`, `WARNING:`, `ERROR`, `pending`). Tables show 50 rows and then `N more rows` (the disagreement list of `Evaluation` shows 20); `Classifier` shows 12 prompt lines then `N more lines in the prompt`, the digest's first 12 characters and the recorded evaluation (or `no evaluation recorded`); `Gold` shows a dev/test/pending/all table of row counts. `.to_polars()` and `.to_pandas()` (always both, through one helper, `_frame.py`) exist on `Candidates`, `Predictions`, `GoldSet`, `EvalLog` and `BandReport`; `Evaluation` has no `.rows`, so its table is `disagreements_to_polars()` and `disagreements_to_pandas()`. Columns are every key of every row in first-seen order (not just the first row's); a missing key is a null/`None`. Verified against polars 2.1 and pandas 3.1: `polars.DataFrame(dict_of_lists, strict=False)` (so ints and floats can share a column; a `labels` list column is `List(String)`) and `pandas.DataFrame` where a column with any `None` is built as `object` so it holds `None`, not `NaN`; an empty table is a `(0, 0)` frame. A missing library raises `ImportError("polars is not installed: pip install polars")` (resp. pandas). `polars` and `pandas` are in the dev dependency group only, and `import hunches` imports neither (tested). `GoldSet`'s two export methods only read; `tests/test_gold.py`'s pin of the public names was updated for them.

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
- **Ctrl-C / interrupting the cell (found in task 03):** while the caller waits, a `KeyboardInterrupt` cancels the worker's main task, waits for it to finish, then re-raises; tested with a real `SIGINT` against a bare outer loop. Two findings: `asyncio.run` installs its own SIGINT handler that only cancels its main task, which cannot run while the main thread is blocked in the sync wrapper, so a script that calls a sync wrapper from inside `asyncio.run` is not interruptible by Ctrl-C (Jupyter does not install that handler, so cells are); and in Python 3.12 `Thread.join()` returned early after an interrupted join, so the wrapper waits on a `threading.Event` the worker sets as its last step instead.
- **Progress:** long calls print a single updating line (done/total, live vs cached, running cost) in a terminal and a notebook; `progress=False` silences it; `progress=callable` receives `(done, total, info)`.
- **Restarting the kernel loses nothing:** artifacts are files and API calls are cached, so re-running the notebook top to bottom is cheap and reproduces the same state.
- **Automated use:** `Classifier.load(...)` or an import, then `clf.classify(new_items, out=...)`. No gold, no UI, no network except the model provider (and the corpus, if searching).

## Agent integration

The skills are the replacement for the in-app assistant. They contain **guidance, not a state machine**.

- `skills/hunches/SKILL.md` (frontmatter `name: hunches`; a `description` that triggers on content analysis / classifying a corpus / gold labels and **ends with the Short gold rule**, within the 1024-character description limit Kiro documents ([Kiro skills](https://kiro.dev/docs/skills/)); the body opens with the Full rule) and `skills/hunches/references/`: `workflow.md` (the idiom above and what to ask the user at each point: the brief, which seeds are true of a match, single vs multi label, what makes a good label description), `tuning.md` (read `ev.disagreements`, change one thing, re-evaluate, stop at the target; never tune on the test split), `running.md` (estimate, show cost, ask, `max_cost`), `reuse.md` (bundles, importing in a pipeline). Reference files load on demand.
- Hard rules in the skill besides the gold rule: never run the full classification without showing the estimate and getting a yes; never evaluate the test split to guide edits; never put API keys or database URLs in a notebook, script or file (environment variables only); never edit a gold file.
- Project instruction block (README, also `hunches.GOLD_RULE_FULL`): the Full gold rule plus pointers, to paste into `AGENTS.md` / `CLAUDE.md` / `.github/copilot-instructions.md`. Covers agents without skills (Copilot in the editor, others).
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
| Cost, cache, timing ledger, `genai-prices` | `cost.py` (`models.py` is gone, see task 11) |
| `Taxonomy`, `GoldRow` models | `taxonomy.py`, `gold.py` |

Changed: functions take explicit arguments instead of reading `Config` and `Path(".hunches")` globally; `search.search` and friends take a corpus object; `cost` takes a cache directory; module-level `_MEMO` caches go.

Removed (the TUI is pulled out completely, with no deprecation period): `app.py`, `screens/`, `theme.py`, `hunches.tcss`, `history.py`, `keys.py`, `system.py`, the model pickers, `files.py`'s state/approval/staleness/versions/chat/pipeline-status code, the `hunches` console script, and the dependencies `textual`, `keyring`, `platformdirs`, `python-dotenv`, `pytest-textual-snapshot`. All TUI tests and the `ui` test marker go. Specs 001–005 stay in the repo as history, each marked superseded in its header.

Not read any more, left alone if present in an old project: `config.toml`, `state.json`, `brief.md`, `chat/`, `history/`, `versions/`, `threshold.json`, `test_result.json`. Still readable: `seeds.csv`, `candidates.jsonl`, `taxonomy.yaml`, `prompt.md`, `gold.jsonl`, `results.jsonl`, `cache/`.

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
- FR-14 `Gold.draw` writes `labels=None`. Labels enter a gold file only through the labelling server (stamped `hunches-ui`) or `import_rows` (stamped `imported`); no other public function sets or edits a label.
- FR-15 `evaluate` skips and counts pending rows, accepts any other well-formed rows (including a file produced elsewhere or by hand), and shows the per-source counts in its repr. It refuses nothing on provenance.
- FR-16 `draw` never returns an id already in the gold file; dev and test are disjoint.
- FR-17 The server meets every item in "The labelling web page": local-only, tokened, offline, autosave, resume, no prediction shown, `single`/`multi`/`off_topic` rules identical to `files.validate_labels`.
- FR-18 The page follows the system colour scheme. Tested without a browser: the served page has `<meta name="color-scheme" content="light dark">`, the served CSS contains `prefers-color-scheme: dark` rules, and the page contains no JavaScript that forces a scheme. The real rendering check is manual (see "Needs a human"). No Playwright or other browser automation dependency is added.
- FR-19 A second `label` on the same gold file is refused while the first runs; a crashed server's stale lock is detected and replaced.
- FR-20 Every `evaluate` call appends exactly one line to the evaluation log with the fields listed under `evaluate`; the log is append-only; `log=False` writes nothing; `eval_log` reads it back and counts test-split evaluations and distinct prompts correctly.

**Reuse**
- FR-21 `save`/`load` round-trips a classifier; `load` warns when the digest differs from the recorded evaluation.
- FR-22 A script with no notebook, no gold file and no UI can `load` and `classify` (test it).

**Agent integration**
- FR-23 The skill, references, `AGENTS.md` snippet, Kiro steering file and plugin manifests exist and validate (`claude plugin validate` for the Claude/Codex manifest).
- FR-24 `src/hunches/gold_rule.md` is the canonical text, exposed as `hunches.GOLD_RULE_SHORT` and `hunches.GOLD_RULE_FULL`. A test asserts the Short form appears verbatim in the skill `description`, and in the output of `repr(Gold)`, `Gold.draw` and `hn.label`; and the Full form in the `SKILL.md` body, the README instruction block and the Kiro steering file. On a mismatch it prints the text to paste.
- FR-25 Docs: the README is rewritten around the notebook flow and the install commands for each harness; `AGENTS.md`/`CLAUDE.md` of this repo are updated (stack, commands, layout, principles) and no longer mention Textual.

## Success criteria

- SC-1 A scripted end-to-end test with `FunctionModel`/`TestModel`, tiny hand-built vectors and a simulated labelling session over HTTP runs the whole chain in the README example and passes, with zero real network calls.
- SC-2 A person who has never seen the TUI can reproduce the README example in a notebook, in order, with each cell's output explaining what happened and what to do next.
- SC-3 Re-evaluating the dev split with an unchanged prompt makes zero live calls; after a prompt change it makes exactly one live call per item and no more (checked by counting `FunctionModel` invocations).
- SC-4 Pre-006 caches and gold files from a real project are readable by the new code (checked by a fixture generated by the old code before it is removed).
- SC-5 Source size of `src/hunches` falls by at least half (it is 11,588 lines today); measured, reported in the final task.
- SC-6 In every location the agent will read, the gold rule is the same text, and a manual trial in each of the four target harnesses ends with the agent refusing a user instruction to label rows.

## Edge cases to cover in tests

Empty candidates; a capped search; `n` larger than available candidates in `draw`; taxonomy changed after labelling (orphans); two prompts evaluated back to back; kernel restart mid-run; `out=` file with rows from a different `run`; unknown model price; a pending gold row in `evaluate`; a gold file produced elsewhere or edited by hand (accepted; unstamped rows are counted in the repr and the log); imported rows whose labels are not in the taxonomy (reported as orphans); a browser tab closed mid-label; a port already in use.

## Out of scope

Technical enforcement of gold integrity (provenance checks that refuse data); a CLI; MCP server; hooks; a persisted status or approval system; undo/redo (use git); web pages for thresholds, results browsing or settings (notebook reprs cover them); multi-annotator labelling and agreement scores; hosting the labelling page for remote people; embedding the corpus; writing to the corpus; a keyring or any key storage.

## Decisions recorded (Chris, 2026-10-26)

1. **The TUI is removed completely**, in this spec, with no deprecation period. `v0.1.0` was never tagged or published.
2. **Existing human-labelled gold datasets are allowed** (`Gold(path)` reads any file in the row schema; `Gold.import_rows`). No restrictive checks; instructions to the agent are the only enforcement, users are responsible, honest and transparent.
3. **Every evaluation run is logged** (all splits), as a history, not a status.
4. **No Playwright.** The dark/light behaviour is covered by HTTP-level tests of the served page and CSS, plus the manual browser check under "Needs a human".
5. **Canonical gold-rule text:** `src/hunches/gold_rule.md` (judgement call, see "The gold rule"): it is package data the library prints at run time, and the copies that must reach agents automatically (skill description, instruction-file block, steering file, skill body) are held in sync by a test.

## Needs a human (stop and report, don't fake)

Installing and exercising the plugin in each of Claude Code, Codex, Copilot CLI and Kiro (the Codex hook trust step does not apply because there are no hooks; check that Codex really picks up `.claude-plugin/marketplace.json`, and that Copilot CLI's marketplace lookup accepts the repo), the gold-rule refusal trial in each (SC-6), a real browser check of the labelling page in light and dark on at least one desktop and one phone-width viewport, a real notebook run in Jupyter and one other notebook (marimo or Colab), and everything 005 already lists (a real pgvector/RDS/S3 corpus, API keys).

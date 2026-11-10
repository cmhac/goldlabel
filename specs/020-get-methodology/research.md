# Research: `gl.get_methodology`

Everything below was read from the code on this branch; no external API is involved, so no external docs were needed (the constitution's "check against docs" rule covers Pydantic AI, psycopg, boto3 and the standard library, and this feature uses only `json`, `dataclasses`, `pathlib`, `datetime` and `html`).

## What each source holds (and does not)

| Source | Holds | Missing |
|---|---|---|
| `Candidates` (`candidates.py`) | rows, `source`, `floor`, `seeds_digest`, `embedding_model`, `capped`; rows carry `best_seed` or `matches` | seed phrases, keywords, regex flag, corpus, filter (added by this feature) |
| `Candidates.above(t)` | `dataclasses.replace(self, rows=...)`; `floor` is **not** changed | the cutoff (added by this feature as `cutoff`) |
| `Gold` (`gold.py`) | path, `candidates` (may be `None`), taxonomy and rows in the file (`sample`, `labels`, `labelled_by`, `labelled_at`, `note`, `revisions`) | the classifier, the run |
| `evals.jsonl` line (`evaluation.py`) | `time`, `samples`, `rows_digest`, `n`, `skipped_pending`, `gold`, `model`, `digest`, `prompt`, `taxonomy`, `metric`, `target`, `score`, `metrics`, `dollars`, `live_calls`, `cached_calls`, `goldlabel`, `disagreements` | nothing needed |
| `Classifier` | `model`, `taxonomy`, `prompt`, `digest`, `evaluation` (set by `load` only) | gold, candidates, run |
| `Predictions` | `rows` (each with `run`, the classifier's digest), `live`, `cached`, `resumed`, `cost`, `errors` | model name, time, prompt text, cutoff (the first two are added by this feature) |
| Cost ledger (`cost.json`) | per-model totals across everything | which stage; not used by this feature |

## Decisions

- **Decision**: reuse `evaluation._history` and `_counts` for the evaluation log, and `_label._revised_after` for STALE. **Rationale**: the sample's own summary and the labelling page already use them, so the methodology cannot disagree with either. **Alternative**: re-parse `evals.jsonl` in the new module; rejected as a second reader of the same format.
- **Decision**: group evaluation lines by their exact `samples` list (`dev`, `test`, `dev+test`). **Rationale**: `_counts` does the same, so "evaluated N times" matches the sample's repr.
- **Decision**: new `Candidates` fields are optional with defaults; `read` uses `meta.get(...)`. **Rationale**: the existing reader already does so for every other key, and `tests/fixtures/pre006/` holds real old files to prove it. **Alternative**: a new meta file beside the candidates; rejected (a second file for the same list).
- **Decision**: `describe(corpus)` returns two short strings, written with plain `if isinstance` branches in `search.py` (the repo's rule for local, S3 and Postgres). `Table`: the file name for a path source, "an in-memory table" or the DataFrame's type otherwise, plus the column names; its `where` as `str(expression)`. `S3Corpus`: bucket, index, region; `where` as JSON. `PgCorpus`: table (and text table), search mode; `where` as the SQL text the user wrote. **Never**: `url_env` value, a URL, `aws_profile`, `auth` secrets. **Rationale**: Principle V and spec FR-005a.
- **Decision**: keyword terms stored as strings; a compiled `re.Pattern` is stored as its `.pattern` and sets `regex` true. **Limit**: its flags are lost (`shortcut:` comment).
- **Decision**: table escaping is `\|` and `<br>` for line breaks, done in one small function. **Alternative**: HTML table; rejected, the output is Markdown.
- **Decision**: the *Run* section's "lowest similarity" is `min(r["max_similarity"] for r in results.rows if "max_similarity" in r)`, omitted when none carry one (keywords or whole corpus); it is stated beside the cutoff, which is a different fact. **Rationale**: it checks the cutoff against what was actually classified.
- **Decision**: `classify` records `run_model` and `run_at` per row, not in a sidecar, under prefixed names. **Why prefixed**: `aclassify` copies every other input field into the row after `run`, so an input column named `model` or `at` (a car forum, a log file) would replace plain `model`/`at` keys, and the methodology would then state the wrong model. **Rationale**: `run` already lives per row and resume keys on it; a sidecar would be a second file to keep in step, and there is no reader for results. **Alternative**: store the prompt per row (rejected: kilobytes times thousands of rows; the digest plus the classifier or the evaluation log proves it).
- **Decision**: `above` stores the cutoff on the returned list. **Rationale**: it is the one place the cutoff is chosen, and `replace` already carries the other fields.
- **Decision**: an evaluation total is `?` as soon as any logged `dollars` is `None`. **Rationale**: Principle VI.
- **Decision**: voice is first person plural, one template per sentence, no options. Sentences for facts that are not recorded are fixed strings so tests can match them.

## Not decided here (belongs to tasks)

The exact sentence wording is the contract in `contracts/get_methodology.md`; the tests hand-write it from there.

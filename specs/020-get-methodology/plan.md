# Implementation Plan: `gl.get_methodology`

**Branch**: `claude/adoring-dirac-igdiww` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-get-methodology/spec.md`

## Summary

A free function `gl.get_methodology(*, candidates, gold, classifier, results, include_gold_table)` returns a `Methodology` (text, stages covered, warnings) built only from the objects passed in and the files beside them. It is one new module, `methodology.py`, that reads what the library already stores (`Gold._read` rows, `evaluation._history` lines, a `Classifier`, a `Predictions`, a `Candidates`) and fills fixed sentence templates; no model, network or file write. Three additive changes elsewhere, all from the spec's clarifications: `Candidates` and `get_candidates` record the seed phrases, keywords, regex flag and a plain description of the corpus and its filter; `Candidates.above(t)` records the cutoff `t`; and `classify` stamps each row it writes with `model` and `at`, beside the `run` digest it already writes. The methodology cannot state those facts otherwise.

## Technical Context

**Language/Version**: Python 3.12+ (the repo's)

**Primary Dependencies**: none new. Standard library only for the new module; it reuses `goldlabel._html.esc`, `goldlabel.gold.Gold/GoldRow`, `goldlabel.evaluation._history/_counts`, `goldlabel._label._revised_after/_when`, `goldlabel.classifier.Classifier`.

**Storage**: plain files, read only: the gold file, `evals.jsonl` beside it, a classifier bundle's `evaluation.json`, the candidates object. The candidates `.meta.json` gains four optional keys; nothing else is written.

**Testing**: pytest, red/green. Gold file and `evals.jsonl` are built by hand as fixtures; expected strings are written by hand in the tests. No model, AWS, database or browser.

**Target Platform**: the library, in a notebook or script.

**Project Type**: library.

**Performance Goals**: under 1 second on the walkthrough analysis (SC-001); one pass over each file.

**Constraints**: read-only, deterministic, no model call, no network, no secrets written (FR-002, FR-004, FR-005a, FR-013).

**Scale/Scope**: a gold file of hundreds of rows; the table is capped only by the caller turning it off.

## Constitution Check

*GATE: passed before Phase 0 and again after Phase 1.*

| Rule | Result |
|---|---|
| I Gold rule | Pass. The module only reads gold rows; it imports no writer, adds no way to set a label, and a test asserts the gold file's bytes are unchanged after the call. |
| II Ponytail | Pass. The skill was invoked before drafting spec and plan (session-long). Ladder: reuses `Gold._read`, `_history`, `_counts`, `_revised_after`, `_html.esc`; no helper class, registry or template engine; f-strings in one function per section. Shortcuts carry `shortcut:` comments (see Complexity). |
| III Spec Kit | Pass. Spec clarified, plan here, tasks next; `/ponytail-review` of spec, plan and tasks runs before `/speckit-implement`. |
| IV Test-first, no real service | Pass. Hand-built fixtures; expected text written by hand; no model is called, so "no model call" is shown by the function never taking a model argument and by a test that runs with `no_real_models` unmodified. |
| V Code is the pipeline, no hidden state | Pass. The function reads only what it is passed (Clarification 2); it never looks in the storage folder on its own, keeps no state and runs no git. Candidates record how they were made in their own file. |
| VI Honest costs, logged evaluations | Pass. Unknown price is `?` (a `None` anywhere in a sum); repeated evaluations of a sample are reported, not policed. |
| VII Notebooks | Partial, justified: no async form (below). Plain `__repr__`, escaped `_repr_html_`; `__all__` gains `get_methodology` and `Methodology`; both documented to the docstring standard (`tests/test_docstrings.py`, ruff `D`). |
| Stack, containers, no new dependency | Pass. No dependency, no container. |

## Project Structure

### Documentation (this feature)

```text
specs/020-get-methodology/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/get_methodology.md
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks
```

### Source Code (repository root)

```text
src/goldlabel/
├── methodology.py        # new: Methodology, get_methodology, one function per section
├── candidates.py         # Candidates gains seeds, keywords, regex, corpus, filter, cutoff; write/read/get_candidates/above fill and read them
├── classifier.py         # aclassify: each row also carries model and at
├── search.py             # describe(corpus) -> (source text, filter text), one function with plain ifs
└── __init__.py           # export get_methodology, Methodology
tests/
├── test_methodology.py   # new
├── test_candidates.py    # meta round trip, above() records the cutoff, old file still reads
├── test_classifier.py    # rows carry model and at, an old out file still resumes
├── test_corpus.py        # describe() for Table, S3Corpus, PgCorpus, no secrets
└── test_public_api.py    # PUBLIC gains the two names
```

**Structure Decision**: one new module beside the others, mirroring `evaluation.py`. Nothing under `skills/`, `docs/` or the README changes (spec "Deliberately skipped").

## Design decisions

1. **Return type.** A frozen dataclass `Methodology(text, stages, warnings)`; `__str__` is `text`; `__repr__` is `text`; `_repr_html_` escapes the text inside `<pre>` (no colour). No subclass of `str`, because `warnings` and `stages` must ride along.
2. **Sync only (FR-014).** The function only reads local files, like `Gold`, `Candidates.read` and `Evaluation.write`, none of which has an async form. There is no loop to block, so `_sync.run` is not needed. Recorded as a justified departure from "every I/O function has an async form", whose purpose is network and model calls.
3. **Evaluations come from the gold file's own log**: `_history(gold.path.parent / "evals.jsonl", gold.path)`. Lines are grouped by their `samples` list; each group reports its latest line (by `time`) and `_counts` for how often and with how many prompts. STALE is `_revised_after(row, when)` over that group's rows (the page's own rule).
4. **Mismatches checked (FR-011)**: the classifier's digest against the digests of the logged lines and against the `run` digests on the result rows; the classifier's taxonomy `model_dump()` against the gold file's taxonomy; gold row ids against the candidates' ids, but only when the candidates carry no `cutoff` (rows below a cutoff are legitimately absent, and `gold.candidates` is usually the uncut list, so an explicit cut list is not flagged as "different"). The classifier's prompt goes in the appendix only when its digest equals the rows' `run` digest; otherwise the text says the prompt of the run is not recorded.
5. **No-gold path**: a classifier loaded from a bundle contributes its `evaluation` dict (samples, n, score, metric, date); with neither gold nor bundle evaluation, the *Evaluation* section is omitted.
6. **Totals**: evaluation cost is the sum of the logged `dollars`; any `None` makes the total `?` with the reason "a price is unknown" (Principle VI).
7. **Run section**: counts from `Predictions` (`rows`, `live`, `cached`, `resumed`, errors), cost from `Predictions.cost`; the model(s) and the first and last `at` from the rows (rows without them are counted and reported as not recorded); the `cutoff` from the candidates when set; and the lowest `max_similarity` among rows that have one.
8. **Candidates recording** (Clarifications 1 and 4): new optional `Candidates` fields `seeds`, `keywords`, `regex`, `corpus`, `filter`, with defaults so every existing construction and every old `.meta.json` still works. `get_candidates` fills them; compiled patterns are stored as their pattern text with `regex` true (`shortcut: a compiled pattern's flags are not recorded, upgrade if a reader needs them`). The corpus description never includes `url_env`'s value, a URL, a key or a profile.
9. **The appendix table** escapes `|` as `\|` and a line break as `<br>`; rows in the gold file's own order; notes never appear. `include_gold_table=False` drops only the table.
9a. **Cutoff**: `above(t)` becomes `replace(self, rows=..., cutoff=t)`; `write` adds `cutoff` to `.meta.json`; `read` uses `meta.get("cutoff")`. With a cutoff the Corpus sentence says how many items it left; without one, how many the search produced.
9b. **Run stamps**: in `aclassify`, the row dict gains `"model": _model_name(self.model)` and `"at": datetime.now(UTC).isoformat()` next to `"run": run`. Resume is untouched: it matches on `run` only, so old files resume and resumed rows keep their own stamps. `Predictions` gets no new field; it is read through its rows.
10. **Spec history**: an earlier version of this plan, and of FR-011, said results carry no digest. That was wrong (`aclassify` writes `run`); the spec is corrected.

## Complexity Tracking

| Departure | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| No async form for `get_methodology` (Principle VII) | It does only local file reads, as `Gold` and `Candidates.read` do | An async wrapper over file reads adds a second function nobody asked for and no event loop is blocked |
| Six new optional fields on `Candidates` and six keys in `.meta.json` (seeds, keywords, regex, corpus, filter, cutoff) | Clarifications 1 and 4: the search and the cutoff must be recorded to be stated | Parsing the notebook, or storing only a digest, cannot give the reader the seed phrases or the cutoff |
| Two new keys, `model` and `at`, on every row `classify` writes (an additive change to an output file) | Clarification 3: the run's model and time must be recorded to be stated | Taking them from the classifier passed in cannot prove which model ran or when; a sidecar file or a reader for results was declined |

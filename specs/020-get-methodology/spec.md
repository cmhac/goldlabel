# Feature Specification: `gl.get_methodology`, a plain-English account of what was done

**Feature Branch**: `claude/adoring-dirac-igdiww`
**Created**: 2026-11-10
**Status**: Draft
**Input**: User description: "Automatic methodology generation: in goldlabel we have a very structured workflow that users follow. A `gl.get_methodology` function that returns a plain-English description of what we did."

## Why

A goldlabel analysis always has the same six steps (connect a corpus, choose candidates, define labels, label gold rows by hand, tune and evaluate a prompt, run the classifier). When the result goes into a story, a paper or a README, someone has to write the methodology section: where the items came from, who labelled what, how accurate the classifier was and how that was measured, and what it cost. That is written by hand today, from memory, and it goes wrong in the ways that matter most to a reader: a number copied from an older evaluation, a test set that was quietly used twice, a "labelled by hand" claim about rows that were imported.

The library already holds most of the facts, in plain files and objects the user already has: the candidates and their `.meta.json`, the gold file (taxonomy, samples, who labelled each row, revisions), `evals.jsonl` (every distinct evaluation: model, full prompt, taxonomy, score, cost, which samples), a saved classifier bundle, a `Predictions` result, and the cost ledger. `get_methodology` reads those and writes the account **from what is on disk and in the objects, never from memory and never from a model**, so every sentence can be checked against a file.

Not everything is recorded today. Measured against the code on this branch (`candidates.py`, `evaluation.py`, `classifier.py`):

- `Candidates` saves only a **digest** of the seeds, not the seeds; keywords, the regex flag, the corpus's `where=` filter and the corpus itself are not saved at all (each row carries its `best_seed` or `matches`, so only seeds that won at least one item are recoverable).
- `Predictions` and its `out` file record neither the cutoff chosen, nor the model, prompt or date of the run; `Predictions` itself carries counts and cost.
- `evals.jsonl` does record model, prompt, taxonomy, score, cost and samples, so evaluation and tuning are fully recoverable.

Decision (Clarifications, 2026-11-10): the candidates file starts recording how the search was run (seed phrases, keywords, regex flag, a description of the corpus and filter), so the methodology can state them. Nothing about a classification run is recorded: the cutoff is not even known to `classify` (`Candidates.above` leaves `floor` unchanged), so the *Run* section states the lowest similarity among the items classified instead. Where a fact is still not recorded (older candidates files, the run's own settings), the function says so in words.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get the methodology of a finished analysis in one call (Priority: P1)

An analyst has run the walkthrough to the end. They call `gl.get_methodology(...)` with the objects they have (candidates, gold, classifier, results) and get a plain-English methodology they can paste into a story's methodology box or a README, covering each step that has evidence.

**Why this priority**: this is the whole feature. Each later story refines honesty and coverage.

**Independent Test**: build the sample analysis (tiny corpus, hand-built gold file as a fixture, a stubbed model), call the function, and compare the text to the facts in the files: every count, name and number in the text appears in the inputs.

**Acceptance Scenarios**:

1. **Given** candidates from seeds, a gold dataset with a labelled `dev` and `test` sample, a classifier evaluated on both, and a `Predictions` result, **When** the user calls `gl.get_methodology` with them, **Then** the text has one short section per step: *Corpus and candidates*, *Labels*, *Gold labels*, *Classifier*, *Evaluation*, *Run*.
2. **Given** the same files and the same arguments, **When** the user calls it twice, **Then** the text is identical (no date of "now", no model call, no randomness).
3. **Given** the result in a notebook cell, **When** the cell displays it, **Then** the text reads as prose with the plain `__repr__` and an escaped HTML form, and `str(result)` is the text to paste.

---

### User Story 2 - The text says only what the files say, and says what is missing (Priority: P1)

The reader of the methodology must be able to trust it. Anything the library does not know is stated as not recorded, never filled in, never guessed.

**Why this priority**: a methodology that sounds right and is wrong is worse than none; this is what separates it from asking a model to "write it up".

**Independent Test**: call it on partial inputs (candidates only; gold with no evaluation; a results object with an unknown price) and check the text names what is missing and never invents it.

**Acceptance Scenarios**:

1. **Given** only candidates, **When** called, **Then** only *Corpus and candidates* is written, and the text says nothing about labels, accuracy or cost (not "unknown": simply no claim).
2. **Given** a results object whose price is unknown, **When** called, **Then** the cost is written as unknown (`?`) with the reason, never `$0`.
3. **Given** candidates saved before this feature (no seed list), **When** called, **Then** the text says the seed list was not recorded; for candidates saved after this feature it gives the seed phrases verbatim.
4. **Given** gold rows imported from a file, **When** called, **Then** the text says they were imported and labelled elsewhere, and does not say they were labelled in the labelling page; rows labelled in the page are described as labelled by people there. The number of people is never stated (it is not recorded).
5. **Given** no argument at all, **When** called, **Then** it raises an error that says which arguments it takes.

---

### User Story 3 - The held-out discipline is visible, and trouble is flagged (Priority: P1)

A reader judging the accuracy number needs to know whether it was earned honestly: which sample it was measured on, how often that sample was evaluated, whether the labels changed afterwards, whether the classifier on the test set is the one that was run.

**Why this priority**: the library logs every evaluation precisely so this can be reported; the methodology is where it is reported.

**Independent Test**: build a gold file and an `evals.jsonl` by hand in which a sample was evaluated twice under two prompts, and one row revised after an evaluation; the text flags both.

**Acceptance Scenarios**:

1. **Given** a `test` sample evaluated once, **When** called, **Then** the text reports its score as measured once on rows labelled before the evaluation.
2. **Given** a sample evaluated more than once (counts as in the sample's own summary), **When** called, **Then** the text says how many times and with how many prompts, in the same sentence as its score.
3. **Given** a row of a scored sample whose label was revised after the evaluation ran (the page's STALE case), **When** called, **Then** the text says that evaluation predates a label revision.
4. **Given** the classifier passed in differs (prompt, model or taxonomy) from the one the evaluations and the results were produced with, **When** called, **Then** the text says so, and does not present the evaluation as describing the classifier that ran.
5. **Given** candidates the gold rows were not drawn from, or a classifier taxonomy that differs from the gold file's, **When** called, **Then** the text says the pieces do not match.

---

### User Story 4 - The full prompt, labels and gold dataset go in verbatim (Priority: P2)

A methodology that says "an LLM classified the posts" is not reproducible. The exact label definitions, the exact prompt and the gold labels a reader can check are part of the account.

**Why this priority**: it matters, but the account is useful without it.

**Independent Test**: the text contains the taxonomy's labels with their descriptions, the classifier's prompt exactly as stored, and a table of every gold row, in a closing section a person can cut off.

**Acceptance Scenarios**:

1. **Given** a classifier, **When** called, **Then** a final *Appendix* gives the model name, the prompt exactly as written (not paraphrased) and each label with its description.
2. **Given** the evaluation history holds more than one prompt, **When** called, **Then** the text says how many prompts were tried; only the prompt of the classifier passed in is given in full.
3. **Given** a gold dataset, **When** called, **Then** the appendix ends with the whole dataset as a Markdown table (`sample`, `id`, `text`, `label`, `labelled by`), so a reader can check every label; **When** called with `include_gold_table=False`, **Then** the table is absent and nothing else changes.

---

### Edge Cases

- **No gold file or no `evals.jsonl`** (a classifier loaded from a bundle in a pipeline): the *Gold* and *Evaluation* sections use the bundle's `evaluation` record if present, and otherwise say there is none.
- **Candidates of source "keywords" or "all"**: described as such (terms matched or whole corpus), with no similarity wording.
- **Capped search** (`capped=True`): the text says items above the floor may be missing.
- **A gold sample with rows pending**: counted, and the text says how many were never labelled and so not scored.
- **Row text and notes**: row text appears only in the appendix gold table (FR-007a); a note's text is never copied anywhere (the page says a note is never sent to a model), only the count of notes appears. A gold file with thousands of rows makes a long table; the caller turns it off with `include_gold_table=False`.
- **Row text that contains `|`, line breaks or Markdown**: escaped so the table renders as one row per item.
- **`evals.jsonl` absent beside a gold file that was moved**: no evaluation claims, and the text says none were found.
- **Failed items in a run**: the count of items that errored is given with the number classified.
- **A very large gold file**: the function reads it once and writes nothing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The library MUST provide `gl.get_methodology`, exported in `goldlabel.__all__`, taking the analysis's objects as optional arguments (candidates, gold dataset, classifier, results) and returning the methodology as plain-English text; at least one argument MUST be given, otherwise it MUST raise an error naming them.
- **FR-002**: The text MUST be built only from the arguments and the files they point at (the candidates file and `.meta.json`, the gold file, `evals.jsonl` beside it, a classifier bundle, the cost ledger); it MUST NOT call a model, an embedding service, a database, the network or a browser, and MUST cost nothing.
- **FR-003**: Every fact in the text (count, name, score, date, price) MUST be traceable to one of those sources; a fact that is not recorded MUST be said to be not recorded, never estimated or filled in.
- **FR-004**: The text MUST be deterministic: the same files and arguments give the same text.
- **FR-005**: *Corpus and candidates* MUST say how the candidates were chosen (the seed phrases verbatim with the embedding model and floor, the keywords and whether they were regular expressions, or the whole corpus), how many there are, what corpus and filter they came from, and whether a backend cap may have hidden items. Each of these is stated only when the candidates file records it.
- **FR-005a**: A candidate search MUST save, in the candidates file's `.meta.json`, the seed phrases, the keywords and regex flag, and a plain-text description of the corpus (its file, table or index name) and of its `where=` filter. It MUST NEVER save a connection string, URL with credentials, key or token. Files saved before this feature MUST still be read unchanged, with those facts reported as not recorded.
- **FR-006**: *Labels* MUST give the mode (one label per item, or every label that applies) and the labels, and say that `off_topic` is built in.
- **FR-007**: *Gold labels* MUST say how many rows each named sample holds, how many are labelled and pending, how rows were labelled (in the labelling page, imported, or unstamped), how many were revised and how many carry a note, and that labels are human judgements. It MUST NOT state a number of labellers, and MUST NOT copy any note's text anywhere in the output (notes are a person's private remarks).
- **FR-007a**: The *Appendix* MUST include the full gold dataset as a Markdown table, one row per gold row, with the columns `sample`, `id`, `text`, `label` and `labelled by` (labelling page, imported, or unstamped), in the order samples and rows appear in the gold file. A pending row shows `(pending)` as its label; a multi-label row lists its labels separated by commas. Text is shown exactly as stored, with `|` and line breaks escaped so the table stays one row per item. Notes and past revisions are not in the table. The table MUST be left out when the caller asks (a single `include_gold_table=False`), because it copies the corpus's own text and can be large; the other sections do not change.
- **FR-008**: *Classifier* MUST name the model and say how many prompts were tried, from the evaluation history.
- **FR-009**: *Evaluation* MUST report, for each evaluated sample, the headline metric and score, the target and whether it was met, the rows scored and skipped as pending, the date of the latest evaluation, how often the sample was evaluated and with how many prompts, and its cost; it MUST flag an evaluation that predates a label revision (STALE), and any sample evaluated more than once.
- **FR-010**: *Run* MUST report how many items were classified (live, cached, resumed, failed), the cost (written as unknown, `?`, when any price is unknown, never `$0`) and, when the items carry similarity scores, the lowest similarity among them. It MUST NOT state a cutoff, a run date or the model and prompt of the run unless they are given by a source (the classifier passed in, the evaluation log); a run's own settings are not recorded.
- **FR-011**: The text MUST name each inconsistency between the pieces it was given (classifier differs from the evaluated one, taxonomy differs from the gold file's, candidates differ from the ones the gold rows came from) instead of describing them as one analysis.
- **FR-012**: The closing *Appendix* MUST give the classifier's model, prompt and labels verbatim.
- **FR-013**: The function MUST be read-only: it MUST NOT create, change or delete any file, and MUST NOT offer or contain any way to set a gold label.
- **FR-014**: It MUST have an async form and a sync form that works inside a running notebook loop only if it does I/O that needs one; otherwise a single plain function is enough (decided in the plan; the rule is that it never blocks a notebook).
- **FR-015**: The result MUST have a plain `__repr__` and a `_repr_html_` that escapes everything and sets no colour, and `str(result)` MUST be the pasteable text.
- **FR-016**: The function MUST have a public docstring in the form the docstring rules require (what it does, `Args:`, `Returns:`, `Raises:`, and that it reads files and writes none).

### Key Entities

- **Methodology**: the returned text, plus the list of the stages it covers and the list of warnings it raised (inconsistencies, stale evaluations, repeated test evaluations), so a caller can test for a warning without parsing prose.
- **Sources**: what the function reads and never changes: candidates (rows and meta), a gold dataset (taxonomy, samples, rows, labelled-by stamps, revisions), the evaluation log, a classifier or saved bundle, a `Predictions` result, the cost ledger.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the walkthrough's finished analysis, one call returns the methodology in under 1 second with zero model calls, zero network calls and zero dollars spent.
- **SC-002**: Every number, name and date in the text can be found in a source file or argument; a reviewer checking 20 sampled statements finds 20 traceable (100%).
- **SC-003**: Two calls over unchanged inputs return byte-identical text.
- **SC-004**: With an unknown price anywhere in the inputs, the text never shows a dollar figure for it (0 occurrences of `$0` for an unknown price).
- **SC-005**: A sample evaluated more than once, a stale evaluation, and a classifier or taxonomy mismatch are each named in the text in 100% of the test cases built for them.
- **SC-006**: Every gold and evaluation file is byte-identical before and after the call.
- **SC-007**: With each input missing in turn, the function still returns text and the text claims nothing about the missing step.
- **SC-008**: The text contains no note text from the gold file (checked by a gold file whose notes contain a marker string), in either the default output or with the table off.
- **SC-009**: The appendix table has exactly one line per gold row (header excluded), including rows whose text holds `|` or line breaks, and with `include_gold_table=False` it has none.
- **SC-010**: A candidate list saved by a search and read back gives the same seed phrases, keywords, regex flag, and corpus and filter description (100% of the cases built for seeds, keywords and whole-corpus searches), contains no string from the corpus's connection settings, and a candidates file saved before this feature still reads.

## Clarifications

### Session 2026-11-10

- Q: Should candidate searches start saving how they were run (seeds, keywords, corpus and filter description)? → A: Yes, option B: the candidates file records the seed phrases, the keywords and regex flag, and a description of the corpus and its filter. Nothing about a classification run is recorded; `classify`, its output file and `Predictions` are unchanged.

### Open

1. **[NEEDS CLARIFICATION: where does it find the gold file and the evaluation log?]** Default: from the `Gold` object passed in (its file, and `evals.jsonl` beside it), the same rule the rest of the library uses. Alternative: with no arguments, also look in the storage folder (`GOLDLABEL_DIR`, then `.goldlabel/`) for the default gold file, candidates and log. The alternative is more convenient and reads files the caller did not name; Principle V says every object carries what it needs.

## Assumptions

- The text is deterministic prose from templates, not model-written; a model-written polish is out of scope (it would cost money, vary between calls, and could say something the files do not).
- The text is Markdown-compatible plain text, in the first person plural ("We drew...") for a methodology box; one voice, no options.
- The reader is a person who did the analysis (or the person reviewing it), not an agent; an agent can call it, but it is not an agent tool and nothing is added to the skills' procedures by this feature.
- Dates are the dates in the files (`written_at`, evaluation `time`), shown as dates; "now" is never written.
- Costs come from the evaluation log, the `Predictions` object and the ledger exactly as they are, with the unknown rule of Principle VI.
- The spent-test rule is a rule for agents; the function reports how often a sample was evaluated and does not police it, like `Sample`'s own summary.

## Deliberately skipped

- A model-written or model-polished methodology (cost, variance, risk of an unfounded sentence).
- Output formats other than text (no `.docx`, no HTML page, no PDF, no file written; the caller saves it).
- Options for tone, length, language or style; one voice.
- Reading the notebook or script to infer steps (the code is not parsed; only the objects and files).
- Describing the corpus's own provenance (who collected it, when): it is not known to the library.
- Counting or naming labellers: not recorded.
- Notes and revision history in the appendix table, example items elsewhere, per-label confusion tables, disagreements (use the evaluation objects and the labelling page for those).
- Appendix tables for anything other than the gold dataset (no candidates table, no results table).
- Any other option: `include_gold_table` is the only switch, because the table copies corpus text and can be long.
- Any change to the skills, README or agent docs (offered as a follow-up).
- A command-line form (`goldlabel methodology`); the console has two commands and stays that way.
- Recording anything about a classification run (cutoff, model, prompt, date): `classify`, its output file and `Predictions` are unchanged.
- Recording the corpus's contents or a connection string; only a plain description of the source and filter is saved.

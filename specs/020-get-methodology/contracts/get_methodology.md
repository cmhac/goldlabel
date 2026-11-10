# Contract: `gl.get_methodology`

## Signature

```python
gl.get_methodology(
    *,
    candidates: Candidates | None = None,
    gold: Gold | None = None,
    classifier: Classifier | None = None,
    results: Predictions | None = None,
    include_gold_table: bool = True,
) -> Methodology
```

- Keyword-only. At least one of the first four is required: `ValueError("give at least one of candidates, gold, classifier or results")`.
- `candidates` wins over `gold.candidates`. Pass the list you classified (the one `above` returned) to get the cutoff; the gold file's own candidates are the uncut list.
- Evaluations are read from `evals.jsonl` beside `gold.path`, never from anywhere else.
- Reads files, writes none, calls no model, no network, no browser. Costs nothing.

## Text skeleton

Markdown, first person plural. A section is written only when its input is given. Sentences below are the fixed templates (`{}` are values from the sources); the tests match them by hand-written strings.

```markdown
## Methodology

### Corpus and candidates
We searched {corpus} for posts similar to {n_seeds} example phrases ("{seed}"; "{seed}"; ...). Each phrase was embedded with {embedding_model}, and we kept every item whose highest similarity to any phrase was at least {floor}. This produced {n} candidates. {capped_sentence}
  (cutoff set) We then kept the items with similarity of at least {cutoff}, which left {n}.
  (keywords)  We selected items containing any of {n_terms} terms ("{term}"; ...), matched as {literal text | regular expressions}. This produced {n} candidates.
  (all)       We used every item of {corpus}, {n} in all.
  filter:     The corpus was filtered with: {filter}.
  not recorded: The seed phrases were not recorded in the candidates file.   |   The keywords were not recorded...   |   The corpus and filter were not recorded...

### Labels
Each item received {exactly one label | every label that applies} from: `a`, `b`, or the built-in `off_topic` (the item matches none of them).

### Gold labels
People labelled items by hand and the classifier was measured against their labels. Dataset "{label}" holds {k} samples: **{name}**: {rows} rows, {labelled} labelled, {pending} pending. {a} labelled in the labelling page, {b} imported (labelled elsewhere), {c} without a record of how they were labelled. {r} labels were revised after they were first set, and {m} rows carry a note. The number of people who labelled is not recorded.

### Classifier
Items were classified by `{model}`. {p} prompt(s) were evaluated against the gold labels. The model, prompt and labels are in the appendix.

### Evaluation
Metric: {metric}; target {target | none}.
- **{samples}**: {score} on {n} labelled rows ({skipped} pending rows not scored), {target met | target not met}, latest evaluation {date}. Evaluated {k} time(s) with {p} prompt(s). {flags}
Evaluation calls cost {$x.xx | ?, a price is unknown}.

### Run
{n} items were classified by `{model}` between {first_at} and {last_at}: {live} by live model calls, {cached} from the cache, {resumed} resumed, {failed} failed. The run cost {$x.xx | ?, a price is unknown}. The similarity cutoff was {cutoff}; the lowest similarity among the items was {s}.
  (rows without model or time) The model and time were not recorded on {k} of the rows.
  (no cutoff) The similarity cutoff was not recorded.
  (digest differs from the classifier passed in) These results were produced by a different classifier from the one passed in, so its prompt is not given as the prompt of the run.

### Warnings
- The {samples} sample was evaluated {k} times with {p} prompts.
- The {samples} evaluation of {date} predates a revision of {r} gold label(s); its score may no longer match the labels.
- The classifier passed in is not the one that was evaluated ({what differs}), or not the one that produced the results.
- The classifier's taxonomy differs from the gold file's.
- {r} gold rows are not among the candidates passed in. (checked only when the candidates have no cutoff)
(none: the section is omitted)

### Appendix
**Model**: `{model}`   **Prompt** (exactly as stored): > {prompt}   **Labels**: - `name`: description ...
**Gold dataset**
| sample | id | text | label | labelled by |
|---|---|---|---|---|
| dev | 17 | text with \| escaped<br>and a break | burnout | labelling page |
| dev | 18 | ... | (pending) | |
```

## Errors

| Condition | Error |
|---|---|
| no input given | `ValueError` naming the four arguments |
| an input of another type | `TypeError` naming the argument |
| a gold file that is not a gold file | `GoldError` from `Gold` (unchanged) |

## Invariants (each has a test)

- Same inputs, same text.
- No gold file, `evals.jsonl` or candidates file changes (bytes compared).
- No note text anywhere; the table is absent with `include_gold_table=False` and nothing else changes.
- An unknown price is never shown as `$0`.
- No string from a corpus's connection settings reaches the candidates file or the text.

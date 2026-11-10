# Data model: `gl.get_methodology`

## `Methodology` (new, returned)

Frozen dataclass.

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | the whole methodology in Markdown, ending with the appendix |
| `stages` | `tuple[str, ...]` | the sections written, in order, from `corpus`, `labels`, `gold`, `classifier`, `evaluation`, `run` |
| `warnings` | `tuple[str, ...]` | one sentence per problem found (also written in the text's *Warnings* section) |

`str(m)` and `repr(m)` are `text`. `_repr_html_` is `text` escaped inside `<pre>` with no colour. It has no method that touches a file or a gold label.

## `Candidates` (changed, additive)

New fields, all optional with these defaults, so existing constructions and old files work unchanged:

| Field | Default | Written when |
|---|---|---|
| `seeds` | `None` | the source is "seeds": the phrases, in order |
| `keywords` | `None` | the source is "keywords": strings, a compiled pattern as its `.pattern` |
| `regex` | `False` | keywords are regular expressions (a compiled pattern sets it) |
| `corpus` | `None` | always by `get_candidates`: a plain description of the source (no secrets) |
| `filter` | `None` | the corpus has a `where=` |
| `cutoff` | `None` | set by `above(t)`; a later `above` replaces it |

`write` adds `seeds`, `keywords`, `regex`, `corpus`, `filter`, `cutoff` to `.meta.json`; `read` uses `meta.get` for each. `above`, `sample` (via `replace`) carry them. Not recorded: `limit`, `server_side`, the cache.

## Result rows (changed, additive)

Every row `classify` writes, in memory and in the `out` file, gains two keys beside `run`:

| Key | Value |
|---|---|
| `model` | the model name as `_model_name(model)` gives it |
| `at` | UTC ISO time the row was finished |

Resume keys on `run` only, so files written before this feature still resume; their rows have neither key and are reported as not recorded. Not stored: the prompt or taxonomy (the `run` digest ties the rows to a classifier).

## Inputs read (never changed)

- Gold dataset: `Gold.path` file (taxonomy dict, rows) and `evals.jsonl` beside it.
- Evaluation line fields used: `time`, `samples`, `digest`, `model`, `prompt`, `metric`, `target`, `score`, `n`, `skipped_pending`, `dollars`.
- Classifier: `model`, `prompt`, `taxonomy`, `digest`, `evaluation`.
- Predictions: `rows` (`run`, `model`, `at`, `max_similarity` when present, `error` when failed), `live`, `cached`, `resumed`, `cost`.

## Validation rules

- No argument: `ValueError` naming the four objects.
- An argument of the wrong type: `TypeError` naming it (a corpus is not accepted; only the four objects).
- `gold` with no file yet: its sections say there are no samples, no error.
- `evals.jsonl` absent or damaged lines: skipped by `_history`, so no evaluation claims.

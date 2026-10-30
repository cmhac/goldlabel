# Data Model: Rename the library to goldlabel

No entity gains or loses a field; one value set changes.

## Provenance stamp (`labelled_by` on a gold row)

| Stored value | Written by | Counted as |
|---|---|---|
| `goldlabel-ui` | the renamed labelling page (new) | labelled through the page |
| `hunches-ui` | the labelling page before the rename (legacy, read only) | labelled through the page |
| `imported` | `Gold.import_rows` | imported |
| absent / anything else | | unstamped |

Rules: stamps are read, never rewritten; both page stamps may be mixed in one file; the summary
and the evaluation provenance count show the page group under the new key (`goldlabel-ui N`).

## Evaluation log line

Same fields. The version key is renamed `hunches` to `goldlabel`; nothing reads it, so old lines
need no handling.

## Name surfaces

Listed with old and new values in [contracts/rename-map.md](contracts/rename-map.md).

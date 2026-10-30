# Data Model: Rename the library to goldlabel

No entity gains or loses a field; one value set changes.

## Provenance stamp (`labelled_by` on a gold row)

| Stored value | Written by | Counted as |
|---|---|---|
| `goldlabel-ui` | the labelling page | labelled through the page |
| `imported` | `Gold.import_rows` | imported |
| absent / anything else | | unstamped |

## Evaluation log line

Same fields. The version key is `goldlabel`.

## Name surfaces

Listed with old and new values in [contracts/rename-map.md](contracts/rename-map.md).

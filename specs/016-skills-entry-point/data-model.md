# Data model: text shapes added

There is no data stored or read by new code. These are the shapes the added skill text must have; tests check them.

## Progress report (what the agent tells the user)
Per stage, one of: **done** (names the evidence seen: the call or file), **unsure** (names why), **not started**. Then one proposed resume stage and the question "start there?". Never includes gold text, labels, keys or URLs.

## Stage guide block (one per stage, in the overview)
`purpose` (one plain sentence) · `you ask` (the user's decisions) · `you show` · `wait for` (the approval) · `then say` (the "Done / Next" line from the existing form).

## Page section
`jobs` (the eight) · `start` (CLI form, notebook form, `force_open_ui=True`) · `joining` (notebook call joins a running page) · `rule` (every revision goes through the page; the agent never edits a gold file) · `after a revision` (evaluations made before it are STALE; evaluate again; a new log line).

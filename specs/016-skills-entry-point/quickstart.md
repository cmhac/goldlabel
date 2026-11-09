# Quickstart: checking 016

## Automated (agent runs these)

```bash
uv run pytest tests/test_skill_stages.py tests/test_skills.py tests/test_docs.py tests/test_cli.py tests/test_gold_rule.py -n0
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
uv build   # wheel still holds goldlabel/skills/* and goldlabel/gold_rule.md
```

Expect: the new assertions fail before the text is written and pass after; every older test passes unchanged.

## Read-through (agent, by hand)

Three fixtures in the scratchpad, each a description a reader follows with the overview alone: an empty folder (resume at `goldlabel-connect`); a notebook with a corpus, a taxonomy and `get_candidates` (resume at `goldlabel-tune`); a notebook through `classify` (sequence complete). Record the result in the task note.

## Human checks (the user; agents never fake them, they go in `AGENTS.md`)

1. In Claude Code and one other agent, with a notebook done through stage 3, call `/goldlabel` once: it reports stages 1 to 3 and offers `goldlabel-tune` (SC-003).
2. Gold-rule refusal trial with the updated skills: ask the agent to fix a label in three phrasings; it points to the page and refuses (SC-004).
3. Ask the agent what the labelling page can do; compare its answer with the page in a real browser.

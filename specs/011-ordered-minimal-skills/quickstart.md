# Quickstart: validating 011

1. `uv run pytest tests/test_skill_stages.py tests/test_skills.py tests/test_docs.py -n0` passes.
2. Delete the `## Next` section of any stage skill: `tests/test_skill_stages.py` fails and names the skill. Put it back.
3. Add a `taxonomy.write("taxonomy.yaml")` or a `def` to a stage skill's python block: the test fails. Put it back.
4. `uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest` pass.
5. Human trial (SC-004, not run by an agent): in Claude Code and one other agent, install with `goldlabel install <agent>`, give the sample brief, and check the agent starts at `goldlabel-connect`, names the next skill at each stage end, writes a notebook with no side files, and offers the earlier stage when asked to jump ahead.

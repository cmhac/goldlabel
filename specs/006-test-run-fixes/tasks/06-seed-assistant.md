# 06 — Seed assistant: prompt and edit/delete tools

Spec: item 9. Depends on 02 (the descriptions are in the context the prompt tells the assistant to use).

**Do: prompt** (`screens/brief.py`, `INSTRUCTIONS`)
- Rewrite so that seeds are written **the way someone would write them in this corpus**, in that voice and register, not as descriptions of the concept. Remove the example "The author describes being laid off" and every "The item/author …" style example; use examples that show the *form* only (a short first-person or reported-speech line, a headline-style line) with a clear statement that the content and register come from the user's brief and the store description. Tell it to use the `# Project` and `# Store` blocks of its context to choose voice and vocabulary, to write several phrasings of the same idea (they are different queries) but never duplicate an existing seed, and to avoid meta-language ("the item discusses", "a post about").
- **Ask before generating**: with no seeds yet, ask two to four short questions first (what counts as a match and what does not; where this text would appear and in whose voice; phrasings to avoid) and call `propose_seeds` only after the user has answered, unless the user explicitly says to go ahead. With existing seeds the assistant may act on a clear request directly.
- Keep it short. This is prompt text; tests can only assert it is present.

**Do: tools** (closures inside `BriefScreen.__init__`, next to `propose_seeds`)
- `replace_seed(number: int, was: str, text: str) -> str`: replaces seed `number` (1-based, as numbered in the `# Current seeds` list the instructions function builds with `numbered(self.seeds)`). If the seed currently at that number is not exactly `was`, change nothing and return a message saying the list has changed, with the current text at that number.
- `delete_seeds(numbers: list[int]) -> str`: deletes those seeds, numbers referring to the list as it was when the call started (apply highest first); any out-of-range or duplicate number makes the whole call change nothing and return which one was wrong.
- Both refuse (return a message, change nothing) while `self.editor is not None`: "The user is editing a seed; try again after they save or discard." They return what changed ("Replaced seed 3", "Deleted seeds 2, 5") so the chat shows it. They write through `self.save(summary, "assistant", group)` so the on-screen list, `seeds.csv` and history all update exactly like `add_seeds`; keep `cursor` valid after a delete.
- **One undo per turn**: `propose_seeds` currently passes `uuid4().hex` per call, so two calls in one turn make two history groups. Use one group per assistant turn instead: set `self.turn_group = uuid4().hex` when a turn starts (handle `ChatPanel.Changed` when `chat.running` becomes true; `run_turn` posts it at the start, including for `reply()` called directly by tests) and use it in all three tools. User edits keep `group=None`. Check how `history.save`/`undo` treat `group` (004) and report; one F6 must reverse everything the turn did.

**Tests (red first, stub models)**
- Instructions: contain the ask-before-generating rule, the corpus-voice rule and the pointer to `# Project`/`# Store`; do not contain "The author describes" or "The item". The numbered current-seeds list still reaches the model.
- Tools: replace changes exactly one seed in `seeds.csv` and the list on screen; `was` mismatch changes nothing and says so; out-of-range number changes nothing; delete of several numbers removes the right ones (hand-computed result); a bad number in the list changes nothing; both refuse while the editor is open; history log shows `source == "assistant"` with the turn's single `group` for a turn that calls `propose_seeds` then `replace_seed` then `delete_seeds`; one F6 reverts all three; F7 redoes; stale-candidates marking works after an assistant delete (004 machinery, just assert the status).
- Drive the tools through a `FunctionModel` that emits the tool calls, so the real agent plumbing is exercised.

**Not in this task**: any change to the Taxonomy or Tuning assistants, a corpus-sampling tool (out of scope in the spec).

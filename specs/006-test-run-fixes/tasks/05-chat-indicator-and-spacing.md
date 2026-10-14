# 05 — Chat: thinking indicator and tool-line spacing

Spec: items 7 and 8. Depends on 04 (same panel).

**Do: indicator**
- A `Static` subclass `ThinkingLine` (id `thinking`) in `app.py`: a spinner glyph plus words, e.g. `⠋ thinking…`, muted colour, frames cycled by `set_interval(0.1)` only while it is displayed. It must not have the class `turn` (`ChatPanel.lines` counts `turn` widgets) and is never written to `chat/<stage>.json` or the model history.
- Mount it in `#messages` and keep it the last child (`ChatPanel.add` mounts lines `before="#live"`; keep the indicator after `#live`, and call `move_child` if needed). `#messages` is anchored, so it stays visible.
- Lifecycle in `run_turn`: shown when the turn starts; hidden when the first text delta arrives (`live.set(...)`) or a tool call starts (`FunctionToolCallEvent`; the running tool line is its own indication); shown again after a `FunctionToolResultEvent` until the next text or tool call; hidden in the `finally`/error path. Keep the logic to a few lines in the existing `on_events` and delta loop.
- Context turns (`send_context`) go through `run_turn`, so they show it too.

**Do: spacing**
- A tool line (`FoldLine` with class `fold-tool`) directly after a user turn or an assistant text turn gets one blank row above it; consecutive tool lines stay tight. Today `ChatPanel.DEFAULT_CSS` has `.turn.first, .fold-tool { margin-top: 0 }`. Textual CSS may not support the adjacent-sibling combinator; verify in 8.2.8 and, if it does not, have `ChatPanel.add` add a class (e.g. `-after-tool`) to a line whose previous line is a tool line and style that. The very first line still has no margin above.
- Applies to every `ChatPanel` (Brief, Taxonomy, Tuning); history restored via `write_messages` follows the same rule.

**Tests (red first)**
- Indicator: with a `FunctionModel` whose response waits on an `asyncio.Event`, the indicator is displayed while the turn is blocked; with a `FunctionModel` that streams text then calls a tool then streams again, it is hidden while text streams and shown between a tool result and the next text (assert by pausing on events); gone after the turn finishes and after a failing turn; not present in `files.load_chat` output.
- Spacing: user turn then tool line has exactly one blank row between their regions (`tool.region.y - prev.region.bottom == 1`... use the actual region API); two consecutive tool lines have none; an assistant text turn then tool line has one; restoring a saved chat gives the same layout.
- `tests/test_sizes.py` still passes.

**Not in this task**: anything about the input box (04).

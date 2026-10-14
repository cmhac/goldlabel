# 12 — Pointer styles

Spec: item 3. Depends on 11 (the clickable rail exists).

**Do**
- Docs: https://textual.textualize.io/styles/pointer/ and https://textual.textualize.io/css_types/pointer/ (30 values; `pointer` is the hand). The style only has an effect in terminals that support the Kitty pointer-shapes protocol (OSC 22); nothing changes elsewhere, and no fallback is needed.
- **Find what already has it**: `grep -rn "pointer" .venv/lib/python3.12/site-packages/textual/widgets/`. At the time of writing `Button`, `Select`, `Input`, `TextArea`, `Checkbox`/toggle buttons, `Tabs`, `Tree`, `Collapsible`, `Switch`, `RadioSet`, `Link` and the `Footer` set it; `DataTable` and `OptionList` did not. Report the actual list.
- In `hunches.tcss`, with class/type selectors (the shared look lives there, not in `DEFAULT_CSS`): `pointer: pointer` for every clickable thing that is not already covered: `FoldLine` (toggles on click), the seed rows and list rows that react to clicks (`SeedRow`, the project list, model picker and History entry lists, `DataTable` and `OptionList` rows wherever the app uses them for selection), the tune/gold/taxonomy items that respond to clicks (grep `on_click`, `@click` and `DataTable`/`OptionList` use in `src/hunches/`), and any other custom clickable widget you find; `not-allowed` for disabled ones that are not Textual buttons. List what you covered in the report.
- **The rail**: it is one widget, so a blanket `pointer: pointer` would also show the hand over the cost block and blank rows. Set `styles.pointer` from `StatusHeader.on_mouse_move` (a click row gets `pointer`, anything else `default`), using the same row map as the click handler from task 11.

**Tests (red first)**: for each selector class, a mounted instance's `styles.pointer == "pointer"` (computed style); a disabled item has `not-allowed`; rail mouse-move over a row sets `pointer`, over the cost area sets `default`. Terminal behaviour itself cannot be tested here.

**Needs a human** (report, do not fake): whether the pointer shape actually changes in macOS Terminal.app and in any other terminal Chris uses. Per Ghostty's OSC 22 table (https://ghostty.org/docs/vt/osc/22) and kitty's docs (https://sw.kovidgoyal.net/kitty/pointer-shapes/), Kitty, Ghostty, Foot and recent iTerm2/xterm support it and VTE and Alacritty do not; Terminal.app is not established.

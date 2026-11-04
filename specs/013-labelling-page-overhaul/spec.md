# Feature Specification: Overhaul the labelling page: split layout, auto-advance, keyboard-first, notes

**Feature Branch**: `claude/eloquent-brown-ngl7t1` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-04

**Status**: Draft

**Input**: GitHub issue [cmhac/goldlabel#18](https://github.com/cmhac/goldlabel/issues/18), "Better layout and keyboard shortcuts for gold dataset UI": "on large enough screens, should put text on left and data entry controls on right. clicking an option should auto-advance. and we need keyboard shortcuts so that users don't have to take their hands off keyboard while labeling. In addition, gold datasets should have the ability to store notes for individual records, to help with tuning edge cases." Follow-up from the user: build the redesign mocked up in the Claude Design canvas (<https://claude.ai/artifact/DJitbNLavrtJ7A6fUVaCgk>, boards: desktop single-label, desktop multi-label with a note, phone dark) and replace the current page with it.

## Where things are today

- The page is `src/goldlabel/web/{index.html,app.js,app.css}`, served by `goldlabel._label`. It is one centred column (`max-w-2xl`): progress, the item text, the label options, a Back / Skip / **Save →** row, a keys hint and a "Labelled so far" table.
- Choosing a label only selects it. A person must then press **Save →**, Enter or →. In `single` mode that is two actions per row.
- Keys today: number = choose, Enter or → = save and next, ← = back. They are handled in one global `keydown` listener that ignores Ctrl/Meta/Alt. There is no key for Skip, and nothing for a text field (there is none).
- A gold row is `GoldRow` in `src/goldlabel/gold.py`: `id`, `text`, `labels`, `split`, `labelled_by`, `labelled_at`, and `extra="allow"`. There is no place for a person's comment on a row.
- The server (`_label.py`) writes a label only because a person's HTTP request says so (`POST /api/label` with `{id, labels}`), stamped `labelled_by: "goldlabel-ui"`. That is gold-rule territory and does not change in kind: see FR-010.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Label a single-label row with one keypress or one click (Priority: P1)

A person labelling in `single` mode presses the label's number (or clicks the label). The row is saved and the next pending row is on screen at once. There is no Save button in this mode. A line under the header confirms what was saved and says that ← goes back, so a wrong key press costs one more key press.

**Why this priority**: it is the core of the issue and halves the actions per row.

**Independent Test**: serve a gold file of `single` mode with three pending rows, drive the page's API as the page does, and check that one label request saves the row and the state it returns is the next pending row; check in the served `app.js` that choosing a label calls the save and that no Save button is rendered in `single` mode.

**Acceptance Scenarios**:

1. **Given** `single` mode and a pending row, **When** the person clicks a label or presses its number, **Then** the label is saved and the next pending row is shown.
2. **Given** a row was just saved, **When** the person presses ←, **Then** the previous row is shown with its saved label highlighted and can be changed by choosing another label (which saves and advances again).
3. **Given** the last pending row is saved, **When** it advances, **Then** the "all rows are labelled" state appears as today, with Back and **Done**.
4. **Given** `multi` mode, **When** the person chooses labels, **Then** nothing is saved or advanced until **Save and next**, Enter or → is used (several labels may apply, so a click cannot be final), and `off_topic` stays exclusive as today.

---

### User Story 2 - Text on the left, data entry on the right (Priority: P1)

On a large screen the item text fills the left column and the controls (labels, note, Back, Skip, Save and next in `multi` mode, key legend) sit in a panel on the right, so the eyes stay on the text and the hand stays on the controls. The panel stays in view while a long text scrolls. On a narrow screen the text comes first and the controls follow it in one column, with large touch targets.

**Why this priority**: it is the first thing the issue asks for and it shapes every other part of the page.

**Independent Test**: the served `index.html` and `app.js` use one responsive two-column layout that switches at a width breakpoint; an ad-hoc browser screenshot at 1280px and at 390px shows two columns and one column (a developer check, not a repository test; the human check stays in `AGENTS.md`).

**Acceptance Scenarios**:

1. **Given** a window at least 1024px wide, **When** a row is shown, **Then** the text is in the left column and the label options, note field and buttons are in the right column.
2. **Given** a window narrower than that, **When** a row is shown, **Then** the page is one column, the text first, with no horizontal scrolling.
3. **Given** a very long text, **When** the person scrolls, **Then** the right panel stays reachable on a large screen.
4. **Given** the system is in dark mode, **When** the page loads, **Then** it is dark with the same layout, readable text, and visible focus (the existing `prefers-color-scheme` behaviour, with no toggle).

---

### User Story 3 - Never take hands off the keyboard (Priority: P1)

Everything the person does for a row has a key, shown on screen: label (number), save and next in `multi` mode (Enter or →), back (←), skip (S), jump to the note (N), leave the note (Esc), and save from inside the note (Ctrl or ⌘ + Enter). While the cursor is in the note field the single-key shortcuts are paused, so typing a note never labels, skips or moves a row, and the page says so while it is true. Esc returns to the labels.

**Why this priority**: the issue states it as the reason for the keyboard work; the note field would otherwise break the existing global shortcuts.

**Independent Test**: in the served `app.js`, check the key handler ignores plain keys when the note field has focus and handles N, Esc, S and Ctrl/⌘+Enter as described.

**Acceptance Scenarios**:

1. **Given** the focus is not in the note field, **When** the person presses N, **Then** the note field takes focus.
2. **Given** the focus is in the note field, **When** the person types digits, letters, ← or →, **Then** they edit the note and no label is chosen, no row is skipped and no row moves.
3. **Given** the focus is in the note field, **When** the person presses Esc, **Then** the focus leaves the field and the single-key shortcuts work again, without losing the typed note.
4. **Given** a label is chosen (or the row already has labels), **When** the person presses Ctrl or ⌘ + Enter in the note field, **Then** the row is saved with that label and note and the page advances.
5. **Given** the person presses S outside the note field, **Then** the row is skipped as the Skip button does today.

---

### User Story 4 - Keep a note on a row for tuning edge cases (Priority: P2)

A person can type an optional note on any row ("two policies in one sentence", "sarcasm"). It is saved with the label, comes back when they go back to the row, and is stored in the gold file as the row's `note`, so it can be read later when tuning the prompt or reading disagreements. A note is never sent to a model.

**Why this priority**: the issue asks for it, but the page works without it.

**Independent Test**: label a row with a note over the API, read the gold file and check the row's `note`; read the state and check the item carries it; label again with an empty note and check the key is gone; label with no `note` key and check an existing note is kept.

**Acceptance Scenarios**:

1. **Given** a pending row, **When** the person saves a label with a note, **Then** the row in the gold file has the labels, `labelled_by: "goldlabel-ui"` and `note` with the text (trimmed).
2. **Given** a row with a note, **When** the person goes back to it, **Then** the note field shows it.
3. **Given** a row with a note, **When** it is saved again with an empty or whitespace-only note, **Then** the note is removed from the file (no `note` key, as for a row that never had one).
4. **Given** a request that carries no `note` at all (an older client), **When** the label is saved, **Then** an existing note is left untouched.
5. **Given** a `note` that is not a string, **When** the request is made, **Then** it is refused with a 400 and the file is unchanged.
6. **Given** a gold file written before this change (rows without `note`), **When** it is read, labelled and rewritten, **Then** it loads and every other key is kept as before.
7. **Given** a note on a skipped row, **When** the person presses Skip, **Then** the note is not saved (a skip writes nothing), and the page says so next to the note field.

---

### User Story 5 - Know where I am (Priority: P3)

The header shows the progress bar and "N / total labelled". A status line (a live region, so screen readers hear it) tells what just happened or what to do next. The "Labelled so far" counts stay.

**Why this priority**: it carries the feedback that makes auto-advance safe, but the page works without the polish.

**Independent Test**: check the served page has a `role="status"` element and the counts table, and that an error from the server is still shown with `role="alert"`.

**Acceptance Scenarios**:

1. **Given** a row was saved, **Then** the status line names the row id and the labels saved.
2. **Given** the server returns an error, **Then** it is shown as an alert as today and the person's selection and note are not lost.

---

### Edge Cases

- Fewer than nine labels is the norm; labels beyond the ninth have no number key (as today) and are chosen by click or Tab and Space or Enter.
- Pressing a number while a row is being saved (a request in flight) must not save a second label for the same row or skip a row.
- A multi-label row going back keeps all its saved labels selected, as today.
- A server that has been stopped: the existing "Cannot reach the labelling server" message stays.
- Gold files from before this change, and `tests/fixtures/pre006/`, still load; `note` is absent from rows that have none, not written as `null`.
- Item text and notes are untrusted text: they are put on the page as text, never as HTML (as `textContent` does today).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: At a viewport width of at least 1024px the page MUST show two columns, the item text on the left and the data-entry panel on the right, and the panel MUST stay in view while a long text scrolls. Below that width the page MUST be one column, text first, with no horizontal scrolling and touch targets of at least 44px.
- **FR-002**: In `single` mode, choosing a label (click, tap or number key) MUST save it and advance to the next pending row at once, with no Save button. In `multi` mode choosing MUST only toggle, with **Save and next** (button, Enter, →) saving and advancing; `off_topic` stays exclusive.
- **FR-003**: After every save the page MUST show, in a live region, the row id and labels saved and that ← goes back; before the first save it MUST say what to do.
- **FR-004**: Every action MUST have a visible key hint on the page and a key: label (1 to 9), save and next in `multi` mode (Enter, →; in `single` mode they re-save a row that already has labels, such as one reached with ←), back (←), skip (S), focus the note (N), leave the note (Esc), save from the note (Ctrl or ⌘ + Enter). Plain keys MUST be ignored while the note field has focus, and the page MUST say so while that is true. A held-down key (auto-repeat) MUST NOT act more than once.
- **FR-005**: The panel MUST have an optional note field for the row, labelled for assistive technology, with its current text restored when the row is shown again.
- **FR-006**: `POST /api/label` MUST accept an optional string `note` next to `id` and `labels`. A string is trimmed; if it is then empty the row's `note` is removed; if the key is absent an existing note is kept; a non-string value MUST be refused with 400. `GET /api/state` MUST include the item's `note` (or `null`).
- **FR-007**: `GoldRow` MUST gain `note: str | None = None`, written to the file only when set, so existing files and `tests/fixtures/pre006/` load and rewrite unchanged. `GoldSet.to_polars()` and `to_pandas()` MUST carry the column like the other fields.
- **FR-008**: A note MUST NOT be sent to any model: the classifier, the evaluation and the cache keep using `text` only, and a test MUST show the prompt for a noted row is unchanged.
- **FR-009**: The page MUST keep working with no external request, no new dependency and no new console command; `app.css` is rebuilt from the page's classes as `web/README.md` describes. Real buttons, a `fieldset` with a `legend` for the labels, a visible focus ring, text contrast of at least 4.5:1, a selected state shown by more than colour (a check mark and a heavier border), `prefers-color-scheme` only (no toggle, no stored theme).
- **FR-010**: Gold rule: a note is a person's comment. It MUST be written only by the labelling server on a person's request (`POST /api/label`) and by `Gold.import_rows` as an imported row's own key, unchanged; nothing else in the repository MAY set one. `src/goldlabel/gold_rule.md` MUST NOT change and the three drift tests MUST pass unchanged. The gold rule's ban on editing a gold file covers notes too.
- **FR-011**: The README's "The labelling page" section, the `goldlabel-tune` skill and any other agent text that describes the page or its keys MUST describe the new behaviour, with one sentence in the tune skill that rows may carry a person's `note` and that it should be read when tuning, and the drift tests (`test_skills.py`, `test_docs.py`) MUST pass.
- **FR-012**: The finished state ("All rows are labelled", Back, **Done**), the end-of-session message, error alerts, the progress bar, the "Labelled so far" counts and the label descriptions MUST keep working as today, at every width.

### Key Entities

- **Note**: an optional, trimmed, free-text string a person attached to one gold row; stored as the row's `note`; read by people and agents, never by a model.
- **Item panel**: the right-hand column holding the labels, note and buttons for the current row; the **item text** is the left-hand column.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In `single` mode a row takes exactly one action (one key or one click) to label and advance, down from two.
- **SC-002**: A person can label every row of a session, add notes, go back, skip and press Done using the keyboard alone (the finished screen's **Done** is reached with Tab).
- **SC-003**: A saved note survives a round trip: label with a note, read the file, read the state, go back; the text is identical after trimming.
- **SC-004**: An ad-hoc browser check at 1280px shows two columns and at 390px one column with no horizontal scroll, in light and dark; the check is reported as a developer check and the human browser check stays listed in `AGENTS.md`.
- **SC-005**: Ruff, ty and pytest pass; `tests/test_gold_rule.py`, `tests/test_skills.py` and `tests/test_docs.py` pass with no change to the gold rule text; the existing label server and page tests pass except those that assert the removed Save button, the old keys line or the old single-column classes, which are updated in this change.
- **SC-006**: A gold file made before this change loads, is labelled through the new page and is rewritten with its other keys intact.

## Deliberately skipped

- A keyboard-shortcuts dialog or the mock-up's "Shortcuts ?" button: the key legend is always on the panel.
- A theme toggle or stored preference (dark mode follows the system, as today).
- Auto-advance in `multi` mode (several labels may apply), and an undo timer or toast with a countdown (← is the undo).
- Saving a note on a skipped row, or a note without a label (a skip writes nothing).
- A note length limit (the request body is already capped at 1 MB), note search, a notes view or export UI, and notes in `GoldSet`'s HTML table.
- Showing notes to the classifier, in evaluation, or in disagreement tables (people and agents read the `note` column).
- Custom or configurable shortcuts, number keys for a tenth label and beyond.
- Highlighting words in the item text, keyword matches, or the classifier's prediction (the page never shows one; the gold rule's reason).
- A redesign of the "All saved", finished or error states, or of the counts table beyond what the new layout needs.
- Changing the labelling server's token, Host checks, lock, port or `gl.label`'s signature and behaviour.
- Playwright or any browser in the tests or dependencies.

## Assumptions

- The mock-up is the guide for layout, hierarchy and keys, not for text: its sample passages and labels were invented. Where it differs from this spec the spec wins: the phone mock-up showed label names without descriptions, but the descriptions stay (people need them), and the mock-up's "Shortcuts ?" button is skipped.
- Auto-advance applies to `single` mode only because the issue says "clicking an option should auto-advance" and a multi-label click cannot be final; `multi` mode keeps an explicit save. Shown to the user in the mock-up and approved with it.
- The breakpoint is Tailwind's `lg` (1024px) as "large enough screens".
- The note field is called `note` (singular) in the file and the API; the page calls it "Note for this row".
- No release or version bump; that is the user's.

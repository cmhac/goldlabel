# 03 — Missing-descriptions popup

Spec: item 5, "Missing descriptions popup (Q4)". Depends on 02.

**Do**
- New `screens/descriptions.py` with `DescriptionsScreen(ModalScreen[None])`, built with `modal_box(...)` (see `app.py`) and titled "Describe this project". It holds the same two text areas and hints as New project (reuse the construction rather than copy it: a small function both screens call is fine, no base class), pre-filled with whichever description already exists. Buttons: `Save  F2` (built with `key_button`, disabled until both fields are non-empty after stripping) and `Quit  ctrl+q`. A one-line `say()` message states why it appeared: "This project has no project or store description. The assistant needs both."
- It cannot be dismissed any other way: no Esc binding, no close button. Verify in Textual 8.2.8 that a `ModalScreen` has no default Esc dismissal and that `ctrl+q` is the app's quit binding (`app.py` near line 456) and works while a `TextArea` has focus; test the key and the button. The app's plain `q` quit must not fire while a text area has focus (typing `q` types a `q`).
- Save writes `config.toml` with `files.write_config(config.model_copy(update=…))` (the current project's config; look at how `project_settings.save` writes it) and dismisses.
- `HunchesApp.check_descriptions()`: if the current project's config has an empty `project_description` or `store_description`, push `DescriptionsScreen`. Call it from `switch_to` after `goto_stage(...)` (`self.call_later(self.check_descriptions)`), so it runs once per project open, after any startup modal and after the outside-edit check, and not on every stage change. A project opened from the Projects list goes through `switch_to` too.
- `check_action` already refuses history/undo/redo-plan on a `ModalScreen`; confirm F3, F4, F5, F8, F9, `n`, `p` do nothing while the popup is open.
- **Tests**: `tests/conftest.py` gets an autouse fixture (same pattern as `quiet_tune_assistant`) that replaces `HunchesApp.check_descriptions` with a no-op unless the test is marked `descriptions` (register the marker in `pyproject.toml`), because 28 test files build configs without descriptions. Update the spec's sentence about fixtures writing descriptions to say this instead. `tests/test_sizes.py` lists the popup.

**Tests (red first, marked `descriptions`)**: the popup appears for a config missing one field and for both; each field is pre-filled when present; Save disabled until both filled and enabled after; saving writes `config.toml`, closes, and the assistants' context now contains the text; Esc and F2-while-invalid do nothing; F3/F4/F5/F8/F9/`n`/`p` do nothing; it does not reappear when moving between stages; it is not shown when both are set; the Quit button ends the app.

**Not in this task**: any layout work on New project (07).

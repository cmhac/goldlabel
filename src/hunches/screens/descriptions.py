"""The popup that asks for the project and store descriptions when a project has none."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea

from hunches import files
from hunches.app import key_button, modal_box, say
from hunches.screens.new_project import compose_about, missing_about


class DescriptionsScreen(ModalScreen[None]):
    """No Esc and no close button: the project is not usable by the assistants without both."""

    BINDINGS: ClassVar = [("f2", "save", "Save")]
    DEFAULT_CSS = """
    DescriptionsScreen { align: center middle; }
    DescriptionsScreen > .modal-box { width: 90%; max-width: 100; height: auto; max-height: 100%; }
    DescriptionsScreen .row { height: auto; }
    DescriptionsScreen .row Label { width: 9; color: $text-muted; }
    DescriptionsScreen .about-row Vertical { width: 1fr; height: auto; }
    DescriptionsScreen .buttons Button { margin-left: 1; }
    """

    def compose(self) -> ComposeResult:
        config = files.read_config()
        with modal_box(Vertical(), "Describe this project"):
            yield Static(id="why")
            yield from compose_about(
                config.project_description or "", config.store_description or ""
            )
            with Horizontal(classes="buttons"):
                yield key_button("Quit", "ctrl+q", id="quit")
                yield key_button("Save", "F2", id="save", variant="success")

    def on_mount(self) -> None:
        say(
            self.query_one("#why", Static),
            "This project has no project or store description. The assistant needs both.",
        )
        self.changed()

    def changed(self) -> None:
        self.query_one("#save", Button).disabled = bool(missing_about(self))

    def on_text_area_changed(self) -> None:
        self.changed()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit":
            self.app.exit()
        else:
            self.action_save()

    def action_save(self) -> None:
        if missing_about(self):
            return
        files.write_config(
            files.read_config().model_copy(
                update={
                    "project_description": self.query_one(
                        "#project-description", TextArea
                    ).text,
                    "store_description": self.query_one(
                        "#store-description", TextArea
                    ).text,
                }
            )
        )
        self.dismiss()

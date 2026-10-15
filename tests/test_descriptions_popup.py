"""Spec 006 task 03: the missing-descriptions popup."""

import pytest
from test_app import make_project
from textual.widgets import Button, TextArea

from hunches import files
from hunches.app import HunchesApp
from hunches.screens.descriptions import DescriptionsScreen
from hunches.screens.project_settings import ProjectSettingsScreen
from hunches.screens.projects import ProjectsScreen

pytestmark = pytest.mark.descriptions


def describe(project: str | None, store: str | None) -> None:
    files.write_config(
        files.read_config().model_copy(
            update={"project_description": project, "store_description": store}
        )
    )


def box(app, name: str) -> TextArea:
    return app.screen.query_one(f"#{name}-description", TextArea)


@pytest.mark.parametrize(
    ("project", "store"), [("find x", None), (None, "tweets"), (None, None)]
)
async def test_popup_appears_for_a_missing_field_and_prefills_the_other(
    tmp_path, monkeypatch, project, store
):
    make_project(tmp_path, monkeypatch)
    describe(project, store)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, DescriptionsScreen)
        assert box(app, "project").text == (project or "")
        assert box(app, "store").text == (store or "")


async def test_no_popup_when_both_are_set(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    describe("find x", "tweets")
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, DescriptionsScreen)
        assert app.stage == 1


async def test_save_is_disabled_until_both_are_filled_then_writes_and_closes(
    tmp_path, monkeypatch
):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        save = app.screen.query_one("#save", Button)
        assert save.disabled
        box(app, "project").text = "find x\nbecause y"
        await pilot.pause()
        assert save.disabled
        box(app, "store").text = "   "
        await pilot.pause()
        assert save.disabled
        box(app, "store").text = "tweets"
        await pilot.pause()
        assert not save.disabled
        await pilot.click("#save", offset=(2, 0))
        await pilot.pause()
        assert not isinstance(app.screen, DescriptionsScreen)
    config = files.read_config()
    assert config.project_description == "find x\nbecause y"
    assert config.store_description == "tweets"
    assert files.project_context() == "# Project\nfind x\nbecause y\n\n# Store\ntweets"
    assert files.assistant_context().startswith(files.project_context())


async def test_f2_saves_only_when_valid(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app.screen, DescriptionsScreen)
        box(app, "project").text = "find x"
        box(app, "store").text = "tweets"
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert not isinstance(app.screen, DescriptionsScreen)
    assert files.read_config().store_description == "tweets"


async def test_escape_and_navigation_keys_do_nothing(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # focus off the text areas so n and p are not typed into them
        app.screen.set_focus(None)
        for key in ("escape", "f3", "f4", "f5", "f8", "f9", "n", "p"):
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, DescriptionsScreen), key
        assert app.stage == 1
        assert not any(
            isinstance(s, (ProjectSettingsScreen, ProjectsScreen))
            for s in app.screen_stack
        )


async def test_q_types_a_q_and_ctrl_q_quits_from_a_text_area(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        box(app, "project").focus()
        await pilot.press("q")
        await pilot.pause()
        assert box(app, "project").text == "q"
        assert not app._exit
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert app._exit


async def test_quit_button_ends_the_app(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#quit", offset=(2, 0))
        await pilot.pause()
        assert app._exit


async def test_not_shown_again_when_moving_between_stages(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        box(app, "project").text = "find x"
        box(app, "store").text = "tweets"
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        describe(None, None)  # still missing on disk, but only opening a project checks
        app.goto_stage(2)
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert not any(isinstance(s, DescriptionsScreen) for s in app.screen_stack)
        assert app.stage == 3


async def test_explains_why_it_appeared(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        text = str(app.screen.query_one("#why").render())
        assert (
            "This project has no project or store description. The assistant needs both."
            in text
        )


async def test_popup_fields_have_a_blank_row_between_them(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        why = screen.query_one("#why")
        rows = list(screen.query(".about-row"))
        buttons = screen.query_one(".buttons")
        assert rows[0].region.y - why.region.bottom == 1
        assert rows[1].region.y - rows[0].region.bottom == 1
        assert buttons.region.y - rows[1].region.bottom == 1

"""006/11: every row of the left rail is clickable and does what its key does."""

import pytest
from test_app import make_project
from test_keep_runs import write_project
from test_stale_ui import write_test_result

from hunches.app import STAGES, HunchesApp, StatusHeader
from hunches.screens.history import HistoryScreen
from hunches.screens.project_settings import ProjectSettingsScreen
from hunches.screens.projects import ProjectsScreen
from hunches.screens.system import SystemSettingsScreen

pytestmark = pytest.mark.usefixtures("system_ready", "stub_taxonomy_assistant")
SIZES = [(100, 30), (120, 36)]


def lines(app) -> list[str]:
    return str(app.screen.query_one(StatusHeader).render()).split("\n")


async def click_row(pilot, label: str) -> None:
    """Click the rail row showing `label`; the line index comes from the rendered rail itself."""
    app = pilot.app
    y = next(i for i, ln in enumerate(lines(app)) if label in ln)
    await pilot.click(StatusHeader, offset=(6, y))
    await pilot.pause()


@pytest.fixture
def project(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)


@pytest.mark.parametrize("size", SIZES)
async def test_each_stage_row_opens_that_stage(tmp_path, monkeypatch, size):
    monkeypatch.chdir(tmp_path)
    write_project(tmp_path)
    write_test_result()  # the test stage shows its metrics
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        for number, label, _ in reversed(STAGES):
            await click_row(pilot, label)
            assert app.stage == number and app.screen is app.stage_screen
        assert len(app.screen_stack) == 2


async def test_clicking_the_current_stage_does_nothing(project):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        await click_row(pilot, STAGES[0][1])
        assert app.screen is screen and len(app.screen_stack) == 2


@pytest.mark.parametrize("size", SIZES)
async def test_destination_rows_open_what_their_keys_open(project, size):
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        base = len(app.screen_stack)
        for label, kind in (
            ("Projects", ProjectsScreen),
            ("Project settings", ProjectSettingsScreen),
            ("System settings", SystemSettingsScreen),
        ):
            await click_row(pilot, label)
            assert isinstance(app.screen, kind) and len(app.screen_stack) == base + 1
            app.pop_screen()
            await pilot.pause()
            assert app.screen is app.stage_screen
        await click_row(pilot, "History")
        assert isinstance(app.screen, HistoryScreen)


async def test_a_stage_row_from_an_overlay_leaves_no_overlay_behind(project):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        base = len(app.screen_stack)
        for label in ("Projects", "Project settings", "System settings"):
            await click_row(pilot, label)
            assert len(app.screen_stack) == base + 1
            await click_row(pilot, STAGES[2][1])
            assert app.stage == 3 and app.screen is app.stage_screen
            assert len(app.screen_stack) == base


async def test_a_destination_row_from_an_overlay_replaces_it(project):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        base = len(app.screen_stack)
        await click_row(pilot, "Projects")
        await click_row(pilot, "Project settings")
        assert isinstance(app.screen, ProjectSettingsScreen)
        assert len(app.screen_stack) == base + 1
        await click_row(pilot, "System settings")
        assert isinstance(app.screen, SystemSettingsScreen)
        assert len(app.screen_stack) == base + 1
        screen = app.screen
        await click_row(pilot, "System settings")  # the current overlay
        assert app.screen is screen and len(app.screen_stack) == base + 1
        app.pop_screen()
        await pilot.pause()
        assert app.screen is app.stage_screen


async def test_history_row_does_nothing_while_a_seed_editor_is_open(project):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#seed-list").focus()
        await pilot.press("a")
        await pilot.pause()
        assert getattr(screen, "editing", False)
        await click_row(pilot, "History")
        assert app.screen is screen


async def test_rail_actions_do_nothing_under_a_modal(project):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await click_row(pilot, "History")
        modal = app.screen
        assert isinstance(modal, HistoryScreen)
        for action in ("stage(4)", "projects", "settings", "system_settings"):
            await app.run_action(action)
            await pilot.pause()
            assert app.screen is modal and app.stage == 1
        await app.run_action("history")
        assert app.screen is modal

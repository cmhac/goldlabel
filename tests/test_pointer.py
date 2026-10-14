"""006/12: clickable things that Textual does not cover get the pointer hand."""

import pytest
from test_app import make_project
from textual.widgets import DataTable, OptionList, SelectionList

from hunches.app import STAGES, FoldLine, HunchesApp, StatusHeader
from hunches.screens.paths import DirTree
from hunches.screens.projects import ProjectsScreen
from hunches.screens.tune import Tab

pytestmark = pytest.mark.usefixtures("system_ready", "stub_taxonomy_assistant")


@pytest.fixture
def project(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)


async def test_custom_clickables_have_the_hand(project, tmp_path):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        widgets = [
            FoldLine("tool", "s", "d"),
            Tab("Chat", "chat"),
            OptionList("a"),
            SelectionList[str](("a", "a")),
            DirTree(tmp_path),
            DataTable(id="dis", cursor_type="row"),
            DataTable(id="timeline", cursor_type="row"),
            DataTable(id="bands", cursor_type="row"),
            DataTable(id="rows", cursor_type="row"),
            DataTable(id="table", cursor_type="row"),
        ]
        await app.screen.mount(*widgets)
        await pilot.pause()
        for w in widgets:
            assert w.styles.pointer == "pointer", w


async def test_read_only_tables_keep_the_arrow(project):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        tables = [DataTable(id="per-label"), DataTable(id="counts")]
        await app.screen.mount(*tables)
        await pilot.pause()
        for t in tables:
            assert t.styles.pointer == "default", t


async def test_project_list_rows_have_the_hand(project):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("f4")
        await pilot.pause()
        assert isinstance(app.screen, ProjectsScreen)
        assert app.screen.query_one(DataTable).styles.pointer == "pointer"


async def test_rail_pointer_follows_the_row_under_the_mouse(project):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        rail = app.screen.query_one(StatusHeader)
        rows = str(rail.render()).split("\n")
        stage = next(i for i, ln in enumerate(rows) if STAGES[2][1] in ln)
        dest = next(i for i, ln in enumerate(rows) if "System settings" in ln)
        blank = next(i for i, ln in enumerate(rows) if not ln.strip())
        cost = next(i for i, ln in enumerate(rows) if "cost" in ln.lower())
        for y, shape in ((stage, "pointer"), (blank, "default"), (dest, "pointer")):
            await pilot.hover(StatusHeader, offset=(6, y))
            await pilot.pause()
            assert rail.styles.pointer == shape, y
            assert app.screen._pointer_shape == shape, y
        await pilot.hover(StatusHeader, offset=(6, stage))
        await pilot.hover(StatusHeader, offset=(6, cost))
        await pilot.pause()
        assert rail.styles.pointer == "default"
        assert app.screen._pointer_shape == "default"

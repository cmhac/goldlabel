"""006/10: a run is never stopped by leaving its stage; the rail shows it; downstream starts wait."""

import asyncio
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from textual.widgets import Button, Static

from hunches import files
from hunches.app import ChatPanel, HunchesApp, StatusHeader
from hunches.screens import run
from hunches.screens.brief import BriefScreen
from hunches.screens.final import FinalScreen
from hunches.screens.progress import RunIndicator
from hunches.screens.run import RunScreen
from hunches.screens.search import SearchScreen
from hunches.screens.threshold import ThresholdScreen

pytestmark = pytest.mark.usefixtures("system_ready")

PROMPT = "Classify."
CALLS: list[str] = []
REAL = run.classify_many


class GatedEmbedder(Embedder):
    """Embeds only after `gate` is set; counts the queries it was asked for."""

    def __init__(self, gate: asyncio.Event):
        super().__init__(TestEmbeddingModel("m"))
        self.gate = gate
        self.asked = 0

    async def embed_query(self, query, *, settings=None):
        self.asked += 1
        await self.gate.wait()
        return EmbeddingResult(
            [[1.0, 0.0]],
            inputs=[query],
            input_type="query",
            model_name="m",
            provider_name="test",
            usage=RequestUsage(input_tokens=3),
        )


def write_project(tmp_path, root=None):
    """Config, an embedded corpus of five items, approved stages up to the threshold, 8 candidates."""
    corpus = tmp_path / "corpus"
    corpus.mkdir(exist_ok=True)
    vectors = [[1, 0], [0.8, 0.6], [0.7, 0.714], [0.62, 0.7846], [0.3, 0.954]]
    np.save(corpus / "vectors.npy", np.array(vectors, np.float32))
    items = [{"id": f"i{i}", "text": f"t{i}"} for i in range(5)]
    (corpus / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in items))
    (corpus / "meta.json").write_text(json.dumps({"embedding_model": "m"}))
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="test",
            corpus_dir=str(corpus),
            embedding_model="m",
        )
    )
    files.write_text("seeds.csv", "seed\nalpha\n")
    files.write_state(
        files.State(
            seeds_approved=True,
            taxonomy_approved=True,
            dev_done=True,
            test_done=True,
            threshold_chosen=True,
        )
    )
    files.write_taxonomy(files.Taxonomy(mode="single", labels=[files.Label(name="a")]))
    files.write_text("prompt.md", PROMPT)
    files.write_text("threshold.json", json.dumps({"threshold": 0.65}))
    digest = hashlib.sha256(json.dumps([PROMPT, "test"]).encode()).hexdigest()
    files.write_text("test_result.json", json.dumps({"prompt_hash": digest}))
    files.write_jsonl(
        "candidates.jsonl",
        [
            {
                "id": str(i),
                "text": f"item {i}",
                "max_similarity": 0.7 if i < 6 else 0.62,
                "best_seed": "alpha",
            }
            for i in range(8)
        ],
    )
    files.write_gold(
        [
            files.GoldRow(id=f"g{i}", text="t", labels=["a"], split=s)
            for s in ("dev", "test")
            for i in range(50)
        ]
    )


@pytest.fixture
def gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_project(tmp_path)
    CALLS.clear()
    event = asyncio.Event()

    async def classifier(messages, info: AgentInfo):
        CALLS.append("classify")
        await event.wait()
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name, {"reasoning": "r", "labels": ["a"]}
                )
            ]
        )

    monkeypatch.setattr(
        run,
        "classify_many",
        lambda texts, prompt, taxonomy, model: REAL(
            texts, prompt, taxonomy, FunctionModel(classifier)
        ),
    )
    return event


def rail(app) -> str:
    return str(app.screen.query_one(StatusHeader).render())


async def start_search(app, pilot, gate_event):
    """Stage 2 with a search that waits on the gate (candidates exist, so the rerun is confirmed)."""
    app.goto_stage(2)
    await pilot.pause()
    search = app.screen
    assert isinstance(search, SearchScreen)
    search.embedder = GatedEmbedder(gate_event)
    await pilot.press("r")
    await pilot.pause()
    await pilot.click("#yes")
    await pilot.pause()
    assert search.searching
    return search


async def start_run(app, pilot):
    app.goto_stage(8)
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, RunScreen)
    await pilot.press("s")
    await pilot.pause(0.2)
    assert screen.running and len(CALLS) == 6
    return screen


async def test_search_keeps_going_when_you_leave_and_downstream_starts_wait(
    gate, stub_taxonomy_assistant
):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        search_gate = asyncio.Event()
        search = await start_search(app, pilot, search_gate)
        await pilot.press("n")
        await pilot.pause()
        assert app.screen is not search and app.stage == 3
        assert search.searching
        assert any(w.is_running and w.group == "run" for w in app.workers)
        assert app.running_stages() == [2]
        text = rail(app)
        assert "▶ running" in text
        assert any(
            ln.startswith(" ") and "▶" in ln and "Search" in ln
            for ln in text.split("\n")
        )
        assert "RUNNING" in str(app.screen.query_one(StatusHeader).tooltip)
        # readers are not blocked, later runs are
        assert app.upstream_running(1) is None and app.upstream_running(3) is None
        assert app.upstream_running(9) is None and app.upstream_running(2) is None
        for stage in (5, 6, 7, 8):
            assert app.upstream_running(stage) == "Search"
        app.goto_stage(7)
        await pilot.pause()
        threshold = app.screen
        assert isinstance(threshold, ThresholdScreen)
        assert not threshold.running
        assert "Search is running." in str(
            threshold.query_one("#note", Static).render()
        )
        result = files.read_text("test_result.json") or ""
        Path(
            ".hunches/test_result.json"
        ).unlink()  # no result yet: Final would start by itself
        app.goto_stage(6)
        await pilot.pause()
        final = app.screen
        assert isinstance(final, FinalScreen)
        assert not final.running
        assert final.query_one("#rerun", Button).disabled
        assert "Search is running." in str(final.query_one("#note", Static).render())
        files.write_text("test_result.json", result)
        app.goto_stage(8)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen)
        assert screen.check_action("start", ()) is False
        assert "Search is running." in str(screen.query_one("#run-status").render())
        await pilot.press("s")
        await pilot.pause()
        assert CALLS == [] and not screen.running
        # back to Search while it still works: the same screen
        app.goto_stage(2)
        await pilot.pause()
        assert app.screen is search and search.searching
        search_gate.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not search.searching
        assert search.embedder.asked == 1  # nothing re-ran
        assert len(search.rows) == 4
        assert app.running_stages() == []


async def test_search_that_finishes_while_hidden_shows_its_results_on_return(
    gate, stub_taxonomy_assistant
):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        search_gate = asyncio.Event()
        search = await start_search(app, pilot, search_gate)
        await pilot.press("n")
        await pilot.pause()
        search_gate.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        fresh = app.screen
        assert isinstance(fresh, SearchScreen) and fresh is not search
        assert len(fresh.rows) == 4 and not fresh.searching
        assert search.embedder.asked == 1
        assert app.kept == {}


async def test_full_run_survives_navigation_without_repeating_calls(gate):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = await start_run(app, pilot)
        for _ in range(3):
            await pilot.press("n")
            await pilot.pause()
            assert app.stage == 9 and screen.running
            assert app.running_stages() == [8]
            await pilot.press("p")
            await pilot.pause()
            assert app.screen is screen and screen.running
            assert len(app.screen_stack) == 2
        gate.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not screen.running
        assert len(CALLS) == 6  # no restart, no duplicates
        assert len(files.read_jsonl("results.jsonl")) == 6
        assert app.running_stages() == []


async def test_stop_still_stops_a_run_you_came_back_to(gate):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = await start_run(app, pilot)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert app.screen is screen
        await pilot.press("x")
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert not screen.running
        assert not any(w.is_running and w.group == "run" for w in app.workers)
        assert app.running_stages() == []


async def test_run_that_finishes_while_hidden_shows_the_finished_state(gate):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = await start_run(app, pilot)
        await pilot.press("n")
        await pilot.pause()
        gate.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        fresh = app.screen
        assert isinstance(fresh, RunScreen) and fresh is not screen
        assert fresh.state(run.pending()) == "complete"
        assert not fresh.query_one(RunIndicator).query_one("#run-button").display
        assert app.kept == {}
        assert len(CALLS) == 6


async def test_repeated_navigation_does_not_grow_the_stack(
    gate, stub_taxonomy_assistant
):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await start_run(app, pilot)
        base = len(app.screen_stack)
        for stage in (3, 8, 2, 8, 5, 8, 9, 8):
            app.goto_stage(stage)
            await pilot.pause()
            assert len(app.screen_stack) == base
        assert list(app.kept) in ([], [8])
        assert len(app.kept) <= 1


async def test_overlays_leave_a_run_alone(gate):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = await start_run(app, pilot)
        for key in ("f3", "f4", "f5", "f8"):
            await pilot.press(key)
            await pilot.pause()
            assert app.screen is not screen
            assert screen.running
            await pilot.press("escape")
            await pilot.pause()
            if app.screen is not screen:
                app.pop_screen()
                await pilot.pause()
            assert app.screen is screen and screen.running
        assert len(CALLS) == 6


async def test_switching_project_still_asks_then_cancels(gate, tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    write_project(other)
    monkeypatch.chdir(tmp_path)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = await start_run(app, pilot)
        await pilot.press("n")  # the run is hidden but alive
        await pilot.pause()
        app.open_project(other)
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert not any(w.is_running and w.group == "run" for w in app.workers)
        assert app.kept == {}
        assert screen not in app.screen_stack
        assert len(app.screen_stack) == 2
        assert app.running_stages() == []


async def test_chat_turn_survives_leaving_brief_and_blocks_nothing(gate):
    release = asyncio.Event()

    async def slow(messages, info: AgentInfo):
        await release.wait()
        yield "Done."

    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(1)
        await pilot.pause()
        brief = app.screen
        assert isinstance(brief, BriefScreen)
        brief.agent.model = FunctionModel(stream_function=slow)
        chat = brief.query_one(ChatPanel)
        chat.send("hello")
        await pilot.pause(0.2)
        assert chat.running
        await pilot.press("n")
        await pilot.pause()
        assert app.stage == 2 and chat.running
        assert app.working(brief)
        assert app.running_stages() == []  # a chat turn is not a stage run
        assert app.upstream_running(8) is None
        assert "▶" not in rail(app)
        assert not app.screen.query_one("#run", Button).disabled
        release.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not chat.running
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, BriefScreen) and app.screen is not brief
        assert app.kept == {}


async def test_narrow_header_shows_a_running_badge_and_stepper_mark(
    gate, stub_taxonomy_assistant
):
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await start_search(app, pilot, asyncio.Event())
        await pilot.pause(0.4)
        assert "RUNNING" in rail(app)
        await pilot.press("n")
        await pilot.pause(0.4)
        text = rail(app)
        assert "▶" in text and "RUNNING" not in text


async def test_kept_screen_keeps_its_timers_and_hears_screen_resume(
    gate, monkeypatch, stub_taxonomy_assistant
):
    ticks, resumes = [], []
    real_tick = SearchScreen.tick
    monkeypatch.setattr(
        SearchScreen, "tick", lambda self: (ticks.append(1), real_tick(self))[1]
    )
    monkeypatch.setattr(
        SearchScreen,
        "on_screen_resume",
        lambda self, event: resumes.append(1),
        raising=False,
    )
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        search_gate = asyncio.Event()
        search = await start_search(app, pilot, search_gate)
        await pilot.press("n")
        await pilot.pause()
        before = len(ticks)
        await pilot.pause(0.8)
        assert len(ticks) > before  # set_interval still fires on the suspended screen
        seen = len(resumes)
        app.goto_stage(2)
        await pilot.pause()
        assert app.screen is search and len(resumes) == seen + 1
        search_gate.set()
        await app.workers.wait_for_complete()


async def test_a_blocked_start_frees_itself_when_the_earlier_run_ends(
    gate, stub_taxonomy_assistant
):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        search_gate = asyncio.Event()
        await start_search(app, pilot, search_gate)
        app.goto_stage(8)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen)
        assert screen.check_action("start", ()) is False
        search_gate.set()
        await app.workers.wait_for_complete()
        await pilot.pause(0.6)
        assert screen.check_action("start", ()) is True
        assert "Search is running." not in str(screen.query_one("#run-status").render())


async def test_clicking_another_stage_in_the_rail_keeps_a_search_running(
    gate, stub_taxonomy_assistant
):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        search_gate = asyncio.Event()
        search = await start_search(app, pilot, search_gate)
        label = files.STAGE_NAMES[2]
        y = next(i for i, ln in enumerate(rail(app).split("\n")) if label in ln)
        await pilot.click(StatusHeader, offset=(6, y))
        await pilot.pause()
        assert app.stage == 3 and app.screen is not search
        assert search.searching and app.running_stages() == [2]
        assert any("▶" in ln and "Search" in ln for ln in rail(app).split("\n"))
        search_gate.set()
        await pilot.pause(0.5)
        assert app.running_stages() == []

import json

import pytest
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from test_brief import rows, setup

from hunches import candidates, files, history
from hunches.app import ChatPanel, HunchesApp
from hunches.screens.brief import BriefScreen

pytestmark = pytest.mark.usefixtures("system_ready")


def test_instructions_ask_first_and_write_in_the_corpus_voice():
    from hunches.screens.brief import INSTRUCTIONS

    text = INSTRUCTIONS.lower()
    assert "# project" in text and "# store" in text
    assert "two to four" in text and "propose_seeds" in text
    assert "go ahead" in text  # the user can skip the questions
    assert "voice" in text and "duplicate" in text
    assert "The author describes" not in INSTRUCTIONS
    assert "The item" not in INSTRUCTIONS
    assert "replace_seed" in INSTRUCTIONS and "delete_seeds" in INSTRUCTIONS


def calls(*steps: tuple[str, str]):
    """A stream function that makes these tool calls one after another, then says Done."""

    start = {}

    async def run(messages, info: AgentInfo):
        # tool returns from earlier turns are in the history too
        total = sum(p.part_kind == "tool-return" for m in messages for p in m.parts)
        done = total - start.setdefault("n", total)
        if done < len(steps):
            name, args = steps[done]
            yield {0: DeltaToolCall(name=name, json_args=args)}
        else:
            yield "Done."

    return run


async def turn(app, pilot, screen, *steps):
    screen.agent.model = FunctionModel(stream_function=calls(*steps))
    await screen.query_one(ChatPanel).reply("go")
    await app.workers.wait_for_complete()
    await pilot.pause()


def tool_results() -> list[str]:
    return [
        str(p.content)
        for m in files.load_chat("brief")
        for p in m.parts
        if p.part_kind == "tool-return"
    ]


async def test_replace_seed_changes_one_seed_and_checks_was(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha", "beta", "gamma"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        await turn(
            app,
            pilot,
            screen,
            ("replace_seed", '{"number": 2, "was": "WRONG", "text": "x"}'),
            ("replace_seed", '{"number": 9, "was": "beta", "text": "x"}'),
        )
        assert candidates.read_seeds() == ["alpha", "beta", "gamma"]
        results = tool_results()
        assert "changed" in results[0] and "beta" in results[0]
        assert "9" in results[1]
        await turn(
            app,
            pilot,
            screen,
            ("replace_seed", '{"number": 2, "was": "beta", "text": "delta"}'),
        )
        assert candidates.read_seeds() == ["alpha", "delta", "gamma"]
        assert rows(screen) == ["alpha", "delta", "gamma"]
        assert history.entries("seeds")[-1]["source"] == "assistant"
        assert "Replaced seed 2" in tool_results()[-1]


async def test_delete_seeds_removes_the_right_ones_or_nothing(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["a", "b", "c", "d", "e"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        for bad in ('{"numbers": [2, 6]}', '{"numbers": [2, 2]}', '{"numbers": [0]}'):
            await turn(app, pilot, screen, ("delete_seeds", bad))
            assert candidates.read_seeds() == ["a", "b", "c", "d", "e"]
        screen.cursor = 4
        await turn(app, pilot, screen, ("delete_seeds", '{"numbers": [5, 2]}'))
        assert candidates.read_seeds() == ["a", "c", "d"]
        assert rows(screen) == ["a", "c", "d"]
        assert screen.cursor == 2
        assert "Deleted seeds 2, 5" in tool_results()[-1]


async def test_tools_refuse_while_the_editor_is_open(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha", "beta"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.query_one("#seed-list").focus()
        await pilot.press("e")
        await pilot.pause()
        await turn(
            app,
            pilot,
            screen,
            ("replace_seed", '{"number": 1, "was": "alpha", "text": "x"}'),
            ("delete_seeds", '{"numbers": [2]}'),
        )
        assert candidates.read_seeds() == ["alpha", "beta"]
        results = tool_results()
        assert len(results) == 2
        assert all("The user is editing a seed" in r for r in results)


async def test_one_turn_is_one_group_and_one_undo(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha", "beta", "gamma"])
    files.write_jsonl(
        "candidates.jsonl",
        [{"id": "c", "text": "t", "max_similarity": 0.7, "best_seed": "alpha"}],
    )
    files.write_text(
        "candidates.meta.json",
        json.dumps(
            {
                "seeds_digest": candidates.seeds_digest(["alpha", "beta", "gamma"]),
                "embedding_model": "m",
            }
        ),
    )
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        before = history.entries("seeds")
        assert files.stage_status()[2][0] == "current"
        await turn(
            app,
            pilot,
            screen,
            ("propose_seeds", '{"seeds": ["delta"]}'),
            ("replace_seed", '{"number": 1, "was": "alpha", "text": "ALPHA"}'),
            ("delete_seeds", '{"numbers": [2]}'),
        )
        assert candidates.read_seeds() == ["ALPHA", "gamma", "delta"]
        new = history.entries("seeds")[len(before) :]
        assert len(new) == 3 and {e["source"] for e in new} == {"assistant"}
        assert len({e.get("group") for e in new}) == 1 and new[0].get("group")
        assert files.stage_status()[2][0] == "stale"
        screen.query_one("#seed-list").focus()
        await pilot.press("f6")
        await pilot.pause()
        assert candidates.read_seeds() == ["alpha", "beta", "gamma"]
        assert files.stage_status()[2][0] == "current"
        await pilot.press("f7")
        await pilot.pause()
        assert candidates.read_seeds() == ["ALPHA", "gamma", "delta"]
        await turn(app, pilot, screen, ("delete_seeds", '{"numbers": [1]}'))
        assert history.entries("seeds")[-1]["group"] != new[0]["group"]

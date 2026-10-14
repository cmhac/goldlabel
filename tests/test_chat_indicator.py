import asyncio
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.models.test import TestModel
from textual.app import App, ComposeResult

import hunches
from hunches import files
from hunches.app import ChatInput, ChatPanel, FoldLine


class Host(App):
    CSS_PATH = str(Path(hunches.__file__).parent / "hunches.tcss")

    def __init__(self, panel: ChatPanel) -> None:
        super().__init__()
        self.panel = panel

    def compose(self) -> ComposeResult:
        yield self.panel


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def agent_with(stream_function) -> Agent:
    return Agent(FunctionModel(stream_function=stream_function))


async def say_hello(messages, info):
    yield "hello"


def thinking(panel: ChatPanel):
    return panel.query_one("#thinking")


async def type_and_send(pilot, panel, text):
    box = panel.query_one("#chat-input", ChatInput)
    box.focus()
    box.text = text
    await pilot.press("enter")


def after_tool_result(messages) -> bool:
    return any(p.part_kind == "tool-return" for p in messages[-1].parts)


async def test_thinking_shows_while_the_model_is_blocked_then_goes():
    gate = asyncio.Event()

    async def stream(messages, info):
        await gate.wait()
        yield "reply"

    panel = ChatPanel("brief", agent_with(stream))
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        assert not thinking(panel).display
        await type_and_send(pilot, panel, "hi")
        await pilot.pause(0.3)
        line = thinking(panel)
        assert line.display
        assert "thinking" in str(line.render())
        assert "turn" not in line.classes
        assert panel.query_one("#messages").children[-1] is line
        gate.set()
        await host.workers.wait_for_complete()
        await pilot.pause()
        assert not thinking(panel).display
        assert panel.query_one("#messages").children[-1] is line
        assert [w.kind for w in panel.lines] == ["user", "assistant"]
    assert "thinking" not in (files.root() / "chat" / "brief.json").read_text()


async def test_thinking_hides_while_text_streams_and_while_a_tool_runs():
    # run_stream treats text that comes before a tool call as the final answer, so the turn is tool then text
    tool_running, second_text = asyncio.Event(), asyncio.Event()
    release_tool, release_second = asyncio.Event(), asyncio.Event()

    async def stream(messages, info):
        if after_tool_result(messages):
            yield "second"
            second_text.set()
            await release_second.wait()
            yield " end"
        else:
            yield {0: DeltaToolCall(name="slow", json_args="{}")}

    agent = agent_with(stream)

    @agent.tool_plain
    async def slow() -> str:
        tool_running.set()
        await release_tool.wait()
        return "finished"

    panel = ChatPanel("brief", agent)
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        await type_and_send(pilot, panel, "go")
        await tool_running.wait()
        await pilot.pause(0.2)
        assert not thinking(panel).display  # the running tool line is the indication
        release_tool.set()
        await second_text.wait()
        await pilot.pause(0.2)
        assert not thinking(panel).display  # second text is streaming
        release_second.set()
        await host.workers.wait_for_complete()
        await pilot.pause()
        assert not thinking(panel).display


async def test_thinking_shows_between_a_tool_result_and_the_next_text():
    release = asyncio.Event()

    async def stream(messages, info):
        if after_tool_result(messages):
            await release.wait()
            yield "after"
        else:
            yield {0: DeltaToolCall(name="quick", json_args="{}")}

    agent = agent_with(stream)

    @agent.tool_plain
    def quick() -> str:
        return "ok"

    panel = ChatPanel("brief", agent)
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        await type_and_send(pilot, panel, "go")
        await pilot.pause(0.4)
        assert thinking(panel).display  # result in, next model call not streaming yet
        release.set()
        await host.workers.wait_for_complete()
        await pilot.pause()
        assert not thinking(panel).display


async def test_thinking_gone_after_a_failing_turn_and_shown_for_context_turns():
    agent = Agent(TestModel())

    def boom(*a, **k):
        raise RuntimeError("no key")

    agent.run_stream = boom  # ty: ignore[invalid-assignment]
    panel = ChatPanel("brief", agent)
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        await type_and_send(pilot, panel, "x")
        await pilot.pause(0.3)
        await host.workers.wait_for_complete()
        assert not thinking(panel).display
    gate = asyncio.Event()

    async def stream(messages, info):
        await gate.wait()
        yield "noted"

    ctx = ChatPanel("taxonomy", agent_with(stream))
    async with Host(ctx).run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(ctx.send_context("# s", "update", "Seeds"))
        await pilot.pause(0.3)
        assert thinking(ctx).display
        gate.set()
        await task
        await pilot.pause()
        assert not thinking(ctx).display


def gap(upper, lower) -> int:
    return lower.region.y - (upper.region.y + upper.region.height)


def call(i: int) -> ModelResponse:
    return ModelResponse(
        parts=[ToolCallPart(tool_name="t", args={}, tool_call_id=str(i))]
    )


def ret(i: int) -> ModelRequest:
    return ModelRequest(
        parts=[ToolReturnPart(tool_name="t", content="r", tool_call_id=str(i))]
    )


async def test_tool_line_spacing_after_text_turns_not_between_tool_lines():
    files.save_chat(
        "brief",
        [
            ModelRequest(parts=[UserPromptPart(content="hello")]),
            call(1),
            ret(1),
            call(2),
            ret(2),
            ModelResponse(parts=[TextPart(content="said")]),
            call(3),
            ret(3),
        ],
    )
    panel = ChatPanel("brief", agent_with(say_hello))
    async with Host(panel).run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        user, t1, t2, said, t3 = panel.lines
        assert [type(w) for w in (t1, t2, t3)] == [FoldLine] * 3
        assert gap(user, t1) == 1  # user turn then tool line
        assert gap(t1, t2) == 0  # consecutive tool lines stay tight
        assert gap(t2, said) == 1
        assert gap(said, t3) == 1  # assistant text then tool line
        assert user.virtual_region.y == 0


async def test_first_line_being_a_tool_has_no_margin_above():
    files.save_chat("brief", [call(1), ret(1)])
    panel = ChatPanel("brief", agent_with(say_hello))
    async with Host(panel).run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        (tool,) = panel.lines
        assert tool.virtual_region.y == 0  # scroll content starts at the first line


async def test_live_turn_has_the_same_spacing():
    async def stream(messages, info):
        if after_tool_result(messages):
            yield "Done."
        else:
            yield {0: DeltaToolCall(name="a", json_args="{}")}

    agent = agent_with(stream)

    @agent.tool_plain
    def a() -> str:
        return "ok"

    panel = ChatPanel("brief", agent)
    host = Host(panel)
    async with host.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await type_and_send(pilot, panel, "go")
        await pilot.pause(0.5)
        await host.workers.wait_for_complete()
        await pilot.pause()
        user, tool, _done = panel.lines
        assert gap(user, tool) == 1

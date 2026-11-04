"""011: the six stage skills are one ordered procedure, and every example is goldlabel calls only.

The stage names, the four headings and the deny-list are written out by hand here on purpose: a
skill that drifts must fail against this text, not against something derived from the skills."""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "src" / "goldlabel" / "skills"
OVERVIEW = SKILLS / "goldlabel" / "SKILL.md"
REFS = SKILLS / "goldlabel" / "references"
STAGES = [
    "goldlabel-connect",
    "goldlabel-search-terms",
    "goldlabel-taxonomy",
    "goldlabel-candidates",
    "goldlabel-tune",
    "goldlabel-run",
]
HEADINGS = ["## Entry check", "## Procedure", "## Exit check", "## Next"]
SIDE_FILES = ("taxonomy.yaml", "prompt.md", "seeds.csv", "taxonomy-notes")
DENIED_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.If,
    ast.IfExp,
    ast.For,
    ast.While,
    ast.With,
    ast.Try,
    ast.Assert,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
    ast.GeneratorExp,
)
# shortcut: a deny-list misses a creative construct; tighten it when a notebook shows one.
DENIED_NAMES = {"open", "Path", "os", "json", "pickle", "load_dotenv"}


def body(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text().partition("\n---\n")[2]


def section(text: str, heading: str) -> str:
    rest = text.partition(heading + "\n")[2]
    return re.split(r"\n## ", rest)[0]


def python_blocks(path: Path):
    return re.findall(r"```python\n(.*?)```", path.read_text(), flags=re.DOTALL)


def test_there_are_exactly_the_overview_and_six_stages():
    assert {p.name for p in SKILLS.iterdir() if p.is_dir()} == {"goldlabel", *STAGES}


@pytest.mark.parametrize("n", range(6), ids=STAGES)
def test_a_stage_has_the_four_parts_in_order(n):
    text = body(STAGES[n])
    assert f"Stage {n + 1} of 6" in text
    at = [text.find(h + "\n") for h in HEADINGS]
    assert all(i >= 0 for i in at), f"{STAGES[n]} lacks one of {HEADINGS}"
    assert at == sorted(at), f"{STAGES[n]} has the parts out of order"
    steps = re.findall(r"^\d+\. ", section(text, "## Procedure"), flags=re.MULTILINE)
    assert len(steps) >= 3, f"{STAGES[n]}: the procedure needs numbered steps"
    assert "If this stage is repeated" in text


@pytest.mark.parametrize("n", range(6), ids=STAGES)
def test_the_closing_line_names_the_next_stage(n):
    nxt = section(body(STAGES[n]), "## Next")
    if n < 5:
        assert f"`{STAGES[n + 1]}`" in nxt and "Tell the user" in nxt
    else:
        assert "Sequence complete" in nxt


@pytest.mark.parametrize("n", range(1, 6), ids=STAGES[1:])
def test_the_entry_check_names_the_previous_stage(n):
    entry = section(body(STAGES[n]), "## Entry check")
    assert f"`{STAGES[n - 1]}`" in entry
    assert "skip" in entry


def test_the_overview_states_the_order_and_the_rules():
    text = OVERVIEW.read_text()
    assert "guide to idioms" not in text and "in the order that fits" not in text
    at = [text.find(f"`{s}`") for s in STAGES]
    assert all(i >= 0 for i in at) and at == sorted(at)
    for phrase in (
        "hard requirement",  # issue #16: always recommend the next step
        "write only goldlabel calls",
        "Jupyter notebook",
        "run-once",
        "Sequence complete",
    ):
        assert phrase in text, phrase


def test_no_agent_facing_guidance_creates_side_files():
    paths = [OVERVIEW, *(SKILLS / s / "SKILL.md" for s in STAGES)]
    paths += [REFS / "workflow.md", REFS / "tuning.md", REFS / "running.md"]
    for path in paths:
        for needle in SIDE_FILES:
            assert needle not in path.read_text(), f"{path.name} says {needle}"


def test_the_notebook_fallback_is_gone():
    assert "cannot edit notebooks" not in (REFS / "workflow.md").read_text()


@pytest.mark.parametrize(
    "path",
    [OVERVIEW, *(SKILLS / s / "SKILL.md" for s in STAGES), *REFS.glob("*.md")],
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_examples_are_goldlabel_calls_only(path):
    for code in python_blocks(path):
        if code.startswith("# user-directed"):
            continue
        for node in ast.walk(ast.parse(code)):
            assert not isinstance(node, DENIED_NODES), (
                f"{path.name}: {type(node).__name__} in\n{code}"
            )
            if isinstance(node, ast.Name):
                assert node.id not in DENIED_NAMES, f"{path.name}: {node.id}"
            if isinstance(node, ast.Attribute):
                assert not node.attr.startswith("write"), f"{path.name}: .{node.attr}"


def test_the_instruction_block_states_the_order_and_the_rule():
    text = (ROOT / "docs" / "agent-instructions.md").read_text()
    assert "in order" in text and "write only goldlabel calls" in text

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


def test_the_overview_checks_progress_before_the_procedure():
    """016: /goldlabel looks at what the user already has and offers the next stage."""
    text = OVERVIEW.read_text()
    assert "## Check progress first\n" in text
    assert text.find("## Check progress first") < text.find("## The procedure")
    check = section(text, "## Check progress first")
    for evidence in (
        "gl.Table", "gl.PgCorpus", "gl.S3Corpus", "seeds", "keywords", "gl.Taxonomy",
        "gl.get_candidates", "candidates.jsonl", "gl.Classifier", "gl.Gold",
        "clf.evaluate", "evals.jsonl", "clf.estimate", "clf.classify", "gold*.json",
    ):  # fmt: skip
        assert evidence in check, evidence
    for phrase in (
        "unsure",
        "the user's yes",
        "Sequence complete",
        "changes and runs nothing",
        "never open gold*.json or evals.jsonl",
        "never read a key, a database URL or a .env",
        "only when nothing is done",
    ):
        assert phrase in check, phrase


def test_the_overview_guides_each_stage_in_plain_words():
    """016: the overview alone is enough to lead a user through the six stages."""
    text = OVERVIEW.read_text()
    guide = section(text, "## The stages in plain words")
    assert guide, "no stage guide"
    starts = [guide.find(f"**`{s}`**") for s in STAGES]
    assert all(i >= 0 for i in starts) and starts == sorted(starts)
    for n, start in enumerate(starts):
        end = starts[n + 1] if n < 5 else len(guide)
        for label in ("Purpose:", "Ask:", "Show:", "Approval:"):
            assert label in guide[start:end], f"{STAGES[n]} lacks {label}"
    talk = section(text, "## How to talk the user through a step")
    for phrase in (
        "what the step is for",
        "show",
        "decision",
        "wait",
        "what comes next",
    ):
        assert phrase in talk, phrase
    assert len(text.splitlines()) <= 150


def test_the_overview_teaches_the_labelling_page():
    """016: what the page does, how to start it, and that it is the only route for revisions."""
    page = section(OVERVIEW.read_text(), "## The labelling and review page")
    assert page, "no page section"
    for phrase in (
        "goldlabel label",
        "gl.label",
        "force_open_ui=True",
        "STALE",
        "jump to a row by id",
        "label the pending rows",
        "revise a label or a note",
        "disagreements",
        "never shows a model's prediction",
        "joins",
        "every revision of a gold label or note goes through the page",
    ):
        assert phrase in page, phrase


def test_no_guidance_offers_a_gold_edit():
    rule = (ROOT / "src" / "goldlabel" / "gold_rule.md").read_text().strip()
    paths = [OVERVIEW, *(SKILLS / s / "SKILL.md" for s in STAGES), *REFS.glob("*.md")]
    paths += [
        ROOT / "docs" / "agent-instructions.md",
        ROOT / ".kiro/steering/goldlabel.md",
    ]
    for path in paths:
        text = path.read_text().replace(rule, "")
        for phrase in (
            "edit gold.json",
            "edit the gold file",
            "open gold.json",
            "change the gold file",
            "update the gold file",
            "gold.jsonl",
        ):  # shortcut: a phrase list misses a new wording; extend it when a trial shows one
            assert phrase not in text, f"{path.name}: {phrase}"


def test_tune_offers_the_page_when_reading_disagreements():
    """016: the disagreement-reading steps point at the page and its STALE flag."""
    procedure = section(body("goldlabel-tune"), "## Procedure")
    reading = procedure[
        procedure.index("4. Evaluate on dev") : procedure.index("7. Stop at")
    ]
    for phrase in (
        "goldlabel label",
        "STALE",
        "evaluate again",
        "ev.disagreements_to_polars()",
    ):
        assert phrase in reading, phrase
    assert "never read its disagreements to write the prompt" in procedure


START_BULLET = (
    "- Start with `goldlabel`: it checks the user's notebook and the storage folder "
    "(`.goldlabel/` by default) for the stages already done and offers the next one, so call it "
    "first whenever you do not know which skill comes next; never skip a stage on that "
    "evidence alone, only on the user's yes."
)


def test_the_start_here_bullet_is_the_same_in_every_copy():
    from goldlabel.cli import POINTERS

    copies = {
        "docs/agent-instructions.md": (
            ROOT / "docs" / "agent-instructions.md"
        ).read_text(),
        ".kiro/steering/goldlabel.md": (
            ROOT / ".kiro/steering/goldlabel.md"
        ).read_text(),
        "cli.POINTERS": POINTERS,
    }
    for name, text in copies.items():
        assert START_BULLET in text, name
        assert "To review or revise gold labels" in text, name

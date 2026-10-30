"""The README and the example stay true: public names only, one instruction block, py == ipynb."""

import ast
import json
import re
from pathlib import Path

import goldlabel

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
INSTRUCTIONS = ROOT / "docs" / "agent-instructions.md"
SAMPLE = ROOT / "examples" / "sample"
PY = SAMPLE / "walkthrough.py"
IPYNB = SAMPLE / "walkthrough.ipynb"


def python_blocks(text):
    return re.findall(r"```python\n(.*?)```", text, flags=re.DOTALL)


def public_names_used(code):
    """Every first-level `gl.X` / `goldlabel.X` and every name in `from goldlabel import ...`."""
    tree = ast.parse(code)
    aliases, names = {"goldlabel"}, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases |= {
                a.asname for a in node.names if a.name == "goldlabel" and a.asname
            }
        if isinstance(node, ast.ImportFrom) and node.module == "goldlabel":
            names += [a.name for a in node.names]
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "goldlabel."
        ):
            raise AssertionError(f"private module import: {node.module}")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            names.append(node.attr)
    return names


def test_readme_python_blocks_use_public_names_only():
    blocks = python_blocks(README.read_text())
    assert len(blocks) >= 4, "the README needs the example chain"
    used = [n for code in blocks for n in public_names_used(code)]
    assert used
    for name in used:
        assert name in goldlabel.__all__, f"README uses goldlabel.{name}, not public"
    for needle in ("gl.get_candidates(", "gl.label(", "gl.evaluate(", "clf.classify("):
        assert any(needle in b for b in blocks), needle
    assert any(".to_polars()" in b for b in blocks)


REMOVED = ("LocalCorpus", "vectors.npy", "items.jsonl")


def test_no_doc_mentions_the_removed_corpus_or_its_folder_layout():
    files = [
        README,
        INSTRUCTIONS,
        ROOT / "AGENTS.md",
        ROOT / ".kiro/steering/goldlabel.md",
    ]
    files += (ROOT / "src" / "goldlabel" / "skills").rglob("*.md")
    files += [SAMPLE / "README.md", PY, IPYNB]
    for path in files:
        for word in REMOVED:
            assert word not in path.read_text(), f"{path.name} still says {word}"


ALREADY_EMBEDDED = re.compile(r"already[- ]embedded|embedded corpus", re.IGNORECASE)


def test_nothing_calls_the_library_embedded_corpus_only():
    import tomllib

    files = [
        README,
        INSTRUCTIONS,
        ROOT / "AGENTS.md",
        ROOT / ".kiro/steering/goldlabel.md",
    ]
    files += [ROOT / "plugin.json", *(ROOT / ".claude-plugin").glob("*.json")]
    files += (ROOT / "src" / "goldlabel" / "skills").rglob("*.md")
    for path in files:
        assert not ALREADY_EMBEDDED.search(path.read_text()), path.name
    description = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert not ALREADY_EMBEDDED.search(description["description"])
    assert not ALREADY_EMBEDDED.search(goldlabel.__doc__ or "")


def test_the_docs_describe_the_three_candidate_sources_and_the_table_format():
    for path in (
        README,
        ROOT / "src/goldlabel/skills/goldlabel/references/workflow.md",
    ):
        text = path.read_text()
        for needle in (
            "get_candidates",
            "gl.Table(",
            "keywords=",
            "server_side=True",
            "vector_column",
            "embedding_model",
            "id_column",
            ".parquet",
            "DataFrame",
            "zero-width",
            "Postgres syntax",
            "ascending id",
            "order is the service's",
        ):
            assert needle in text, f"{path.name} does not mention {needle}"
    assert (
        "gl.get_candidates("
        in (ROOT / "src/goldlabel/skills/goldlabel/SKILL.md").read_text()
    )


def test_readme_tables_use_polars_and_mention_pandas():
    text = README.read_text()
    assert "to_pandas()" in text
    assert "pandas" not in "\n".join(python_blocks(text)).replace("to_pandas", "")


def test_readme_holds_the_instruction_block_verbatim():
    readme = README.read_text()
    assert goldlabel.GOLD_RULE_FULL in readme, (
        f"README.md must contain the Full gold rule verbatim. Paste this:\n\n{goldlabel.GOLD_RULE_FULL}\n"
    )
    block = INSTRUCTIONS.read_text().partition("## The block\n\n")[2].strip()
    assert block, "docs/agent-instructions.md has no block"
    assert block in readme, (
        "the block in README.md drifted from docs/agent-instructions.md; "
        f"paste this into the README:\n\n{block}\n"
    )


def test_readme_says_what_it_must_say():
    text = README.read_text()
    for needle in (
        "pip install goldlabel",
        "goldlabel[s3]",
        "goldlabel[pg]",
        "goldlabel[rds]",
        "goldlabel[local]",
        "/plugin marketplace add cmhac/goldlabel",
        "/plugin install goldlabel@goldlabel",
        "copilot plugin marketplace add cmhac/goldlabel",
        "codex plugin marketplace add cmhac/goldlabel",
        ".kiro/steering/goldlabel.md",
        "keyring",
        ".env",
        "evals.jsonl",
        "unverified",
        "never write",
    ):
        assert needle in text, needle


# --- the example ------------------------------------------------------------------------------


def py_cells():
    """`# %%` cells of the script as (type, source); markdown cells are `# %% [markdown]`."""
    cells = []
    for chunk in re.split(r"^# %%", PY.read_text(), flags=re.MULTILINE)[1:]:
        head, _, body = chunk.partition("\n")
        if "[markdown]" in head:
            text = "\n".join(re.sub(r"^# ?", "", x) for x in body.strip().splitlines())
            cells.append(("markdown", text))
        else:
            cells.append(("code", body.strip()))
    return cells


def test_walkthrough_script_and_notebook_hold_the_same_cells():
    nb = json.loads(IPYNB.read_text())
    from_nb = [(c["cell_type"], "".join(c["source"]).strip()) for c in nb["cells"]]
    assert from_nb == py_cells()
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None


def test_walkthrough_is_honest_about_gold_and_keys():
    code = "\n".join(src for kind, src in py_cells() if kind == "code")
    ast.parse(code)
    assert "gl.label(" in code and "gold.draw(" in code
    for bad in ("labelled_by", "import_rows", "api_key", "sk-", "postgres://"):
        assert bad not in code, bad
    assert not re.search(r"\blabels\s*=\s*\[", code)  # no hand-written gold rows
    for name in public_names_used(code):
        assert name in goldlabel.__all__, name
    assert not (SAMPLE / ".goldlabel" / "config.toml").exists()


def test_agents_md_holds_the_rule_and_claude_md_is_its_symlink():
    agents = ROOT / "AGENTS.md"
    assert goldlabel.GOLD_RULE_FULL in agents.read_text(), (
        f"AGENTS.md must contain the Full gold rule verbatim. Paste this:\n\n{goldlabel.GOLD_RULE_FULL}\n"
    )
    assert (ROOT / "CLAUDE.md").is_symlink()
    assert (ROOT / "CLAUDE.md").resolve() == agents.resolve()
    text = agents.read_text().lower()
    assert (
        "# agents.md" in text and "textual tui" not in text.split("## current state")[0]
    )

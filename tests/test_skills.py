"""006 task 16: the skill, its references, the instruction block, the Kiro steering file and the
plugin manifests. The gold rule copies must equal `src/goldlabel/gold_rule.md` (FR-24); a mismatch
prints the text to paste."""

import ast
import dataclasses
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import goldlabel
from goldlabel import GOLD_RULE_FULL, GOLD_RULE_SHORT

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "goldlabel"
SKILL = SKILL_DIR / "SKILL.md"
REFS = ["workflow.md", "tuning.md", "running.md", "reuse.md"]
INSTRUCTIONS = ROOT / "docs" / "agent-instructions.md"
STEERING = ROOT / ".kiro" / "steering" / "goldlabel.md"
CLAUDE_PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
ROOT_PLUGIN = ROOT / "plugin.json"
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
AGENT_PLUGINS_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}


def split_frontmatter(text):
    assert text.startswith("---\n"), "front matter must be the first thing in the file"
    head, _, body = text[4:].partition("\n---\n")
    return yaml.safe_load(head), body


def paste_help(where, form, text):
    return f"\n\n{where} must contain the {form} gold rule verbatim. Paste this:\n\n{text}\n"


def python_blocks(path):
    return re.findall(r"```python\n(.*?)```", path.read_text(), flags=re.DOTALL)


# --- the skill ------------------------------------------------------------------------------


def test_skill_frontmatter():
    meta, body = split_frontmatter(SKILL.read_text())
    assert meta["name"] == "goldlabel" == SKILL_DIR.name
    assert (
        re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"])
        and len(meta["name"]) <= 64
    )
    assert isinstance(meta["description"], str)
    assert 0 < len(meta["description"]) <= 1024
    for key in ("content analysis", "seed", "gold"):
        assert key in meta["description"].lower()
    assert body.strip()


def test_description_ends_with_the_short_rule():
    meta, _ = split_frontmatter(SKILL.read_text())
    assert meta["description"].endswith(GOLD_RULE_SHORT), paste_help(
        "the `description` in skills/goldlabel/SKILL.md (as its last sentence)",
        "Short",
        GOLD_RULE_SHORT,
    )


def test_body_opens_with_the_full_rule():
    _, body = split_frontmatter(SKILL.read_text())
    assert body.lstrip().startswith(GOLD_RULE_FULL), paste_help(
        "the body of skills/goldlabel/SKILL.md (as its first lines)",
        "Full",
        GOLD_RULE_FULL,
    )


def test_instruction_block_and_steering_hold_the_full_rule():
    assert GOLD_RULE_FULL in INSTRUCTIONS.read_text(), paste_help(
        "docs/agent-instructions.md", "Full", GOLD_RULE_FULL
    )
    assert GOLD_RULE_FULL in STEERING.read_text(), paste_help(
        ".kiro/steering/goldlabel.md", "Full", GOLD_RULE_FULL
    )


def test_steering_is_always_included():
    text = STEERING.read_text()
    meta, body = split_frontmatter(text)
    assert meta == {"inclusion": "always"}
    assert body.lstrip().startswith(GOLD_RULE_FULL)


def test_instruction_block_names_every_harness_file():
    text = INSTRUCTIONS.read_text()
    for name in (
        "AGENTS.md",
        ".github/copilot-instructions.md",
        "CLAUDE.md",
        ".kiro/steering",
    ):
        assert name in text
    for ref in REFS:
        assert f"skills/goldlabel/references/{ref}" in text


def test_skill_lists_every_reference_and_they_exist():
    text = SKILL.read_text()
    linked = set(re.findall(r"references/([\w-]+\.md)", text))
    assert linked == set(REFS)
    for name in REFS:
        assert (SKILL_DIR / "references" / name).read_text().strip()
    on_disk = {p.name for p in (SKILL_DIR / "references").iterdir()}
    assert on_disk == set(REFS)


def test_skill_hard_rules_are_stated():
    text = SKILL.read_text().lower()
    for phrase in (
        "estimate",  # never run the full classification without showing it
        "test split",
        "environment variable",
        "gold file",
    ):
        assert phrase in text


# --- code samples ---------------------------------------------------------------------------

DOCS = [SKILL, *(SKILL_DIR / "references" / n for n in REFS)]

# variable name used in the samples -> the class it holds
VARS = {
    "clf": goldlabel.Classifier,
    "gold": goldlabel.Gold,
    "ev": goldlabel.Evaluation,
    "final": goldlabel.Evaluation,
    "candidates": goldlabel.Candidates,
    "est": goldlabel.Estimate,
    "taxonomy": goldlabel.Taxonomy,
}


def has_attr(cls, name):
    if hasattr(cls, name) or name in getattr(cls, "model_fields", {}):
        return True
    return dataclasses.is_dataclass(cls) and name in {
        f.name for f in dataclasses.fields(cls)
    }


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_code_blocks_parse_and_use_real_names(path):
    blocks = python_blocks(path)
    if path.name != "SKILL.md":
        assert blocks, f"{path.name} needs concrete code"
    for code in blocks:
        tree = ast.parse(code)
        for chain in re.findall(r"\b(?:gl|goldlabel)((?:\.\w+)+)", code):
            obj = goldlabel
            for part in chain.lstrip(".").split("."):
                assert hasattr(obj, part), (
                    f"{path.name}: goldlabel{chain} does not exist"
                )
                obj = getattr(obj, part)
        for name in re.findall(r"from goldlabel import ([\w, ]+)", code):
            for n in name.split(","):
                assert hasattr(goldlabel, n.strip()), (
                    f"{path.name}: goldlabel.{n.strip()}"
                )
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                var, attr = node.value.id, node.attr
                if var in VARS and not attr.startswith("_"):
                    assert has_attr(VARS[var], attr), (
                        f"{path.name}: {var}.{attr} does not exist"
                    )


def test_samples_keep_secrets_and_gold_edits_out():
    for path in DOCS:
        for code in python_blocks(path):
            assert not re.search(
                r"sk-[A-Za-z0-9]{8}|postgres(ql)?://|AKIA[A-Z0-9]{8}", code
            )
            assert "api_key=" not in code
            assert "labelled_by" not in code
            # no sample builds gold rows by hand or writes the gold file
            assert "gold.jsonl" not in code or "open(" not in code


def test_the_samples_cover_the_main_calls():
    all_code = "\n".join(c for p in DOCS for c in python_blocks(p))
    for needle in (
        "gl.get_candidates(",
        "gl.Taxonomy(",
        "gl.Classifier(",
        "gl.Gold(",
        "gold.draw(",
        "gl.label(",
        "gl.evaluate(",
        "clf.estimate(",
        "clf.classify(",
        "max_cost=",
        "clf.save(",
        "gl.Classifier.load(",
        "gl.band_sample(",
        "gl.eval_log(",
        "gold.import_rows(",
        "clf.with_prompt(",
        ".to_polars()",
        "disagreements",
    ):
        assert needle in all_code, needle


# --- manifests ------------------------------------------------------------------------------


def load(path):
    return json.loads(path.read_text())


def test_claude_plugin_manifest():
    m = load(CLAUDE_PLUGIN)
    assert m["name"] == "goldlabel"
    assert not m["name"].startswith(("claude-", "anthropic-"))
    assert m["description"] and m["version"]
    assert "hooks" not in m


def test_marketplace_manifest():
    m = load(MARKETPLACE)
    assert m["name"] == "goldlabel"
    assert not m["name"].startswith(("claude-", "anthropic-"))
    assert m["owner"]["name"]
    (plugin,) = m["plugins"]
    assert plugin["name"] == "goldlabel"
    assert plugin["source"] == "./"
    assert "hooks" not in plugin


def test_root_plugin_json_is_agent_plugins_1_0():
    m = load(ROOT_PLUGIN)
    assert m["$schema"] == SCHEMA
    assert (
        re.fullmatch(r"[a-z0-9]+([.-][a-z0-9]+)*", m["name"]) and len(m["name"]) <= 64
    )
    assert m["name"] == "goldlabel"
    assert set(m) <= AGENT_PLUGINS_FIELDS, (
        "the 1.0 manifest is closed; no component paths"
    )
    assert (
        ROOT / "skills" / "goldlabel" / "SKILL.md"
    ).is_file()  # fixed location `skills/`
    assert not (ROOT / "hooks").exists()


def test_versions_agree():
    assert load(CLAUDE_PLUGIN)["version"] == load(ROOT_PLUGIN)["version"]


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_claude_plugin_validate():
    r = subprocess.run(
        ["claude", "plugin", "validate", str(ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_skill_and_its_references_never_mention_the_removed_corpus():
    for path in [SKILL, *(SKILL_DIR / "references" / r for r in REFS)]:
        for word in ("LocalCorpus", "vectors.npy", "items.jsonl"):
            assert word not in path.read_text(), f"{path.name} still says {word}"

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# History keeps the old name; so do the few places that read what was written under it.
HISTORY = ("specs/", "tests/fixtures/pre006/README.md", "tests/test_no_old_name.py")
LEGACY = {  # exact file -> the old-name text it may contain
    "src/goldlabel/gold.py": ["hunches-ui"],
    "tests/test_gold.py": ["hunches-ui"],
    "tests/test_evaluation.py": ["hunches-ui", '"hunches"'],
    "tests/test_notebook.py": ["hunches-ui"],
    "tests/test_gold_rule.py": ["hunches-ui", '"hunches"'],
    "tests/test_settings.py": ["HUNCHES_DIR"],
}
MIGRATION = re.compile(
    r"<!-- legacy-name:start -->.*?<!-- legacy-name:end -->", re.DOTALL
)


def test_the_old_name_appears_only_where_it_is_allowed():
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    left = []
    for f in files:
        if f.startswith(HISTORY) or f == "uv.lock":
            continue
        if re.search("hunches", f, re.IGNORECASE):
            left.append(f)
            continue
        try:
            text = (ROOT / f).read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        if f in ("README.md", "AGENTS.md", "CLAUDE.md"):
            text = MIGRATION.sub("", text)
        for token in LEGACY.get(f, []):
            text = text.replace(token, "")
        if re.search("hunches", text, re.IGNORECASE):
            left.append(f)
    assert left == []

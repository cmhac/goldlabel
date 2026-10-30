import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Built from pieces so that this file does not contain the words it forbids.
OLD_NAME = "hun" + "ches"
OLD_ALIAS = r"\b" + "h" + "n" + r"\b"


def test_the_old_name_and_alias_appear_only_in_the_specs():
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    left = []
    for f in files:
        if f.startswith("specs/") or f in ("uv.lock", "tests/test_no_old_name.py"):
            continue
        try:
            text = (ROOT / f).read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        if re.search(OLD_NAME, f + text, re.IGNORECASE) or re.search(OLD_ALIAS, text):
            left.append(f)
    assert left == []

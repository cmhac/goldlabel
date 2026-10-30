import importlib.util
import subprocess
import sys

KEPT = ["search", "candidates", "classifier", "cost", "metrics"]
REMOVED = [
    "app",
    "screens",
    "theme",
    "history",
    "files",
    "system",
    "keys",
    "models",
]


def test_kept_modules_import_no_textual():
    code = (
        "import sys\n"
        + "".join(f"import goldlabel.{m}\n" for m in KEPT)
        + "assert not [m for m in sys.modules if m.split('.')[0] == 'textual'], 'textual imported'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_tui_modules_are_gone():
    for name in REMOVED:
        assert importlib.util.find_spec(f"goldlabel.{name}") is None, name

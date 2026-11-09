import ast
import subprocess
import sys
from pathlib import Path

from goldlabel.settings import resolve, settings


def test_default_root_is_dot_goldlabel():
    assert settings.root == Path(".goldlabel")


def test_goldlabel_dir_sets_the_initial_value():
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "from goldlabel.settings import settings; print(settings.root)",
        ],
        env={"GOLDLABEL_DIR": "/some/where", "PATH": ""},
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "/some/where"


def test_unset_environment_gives_default_in_subprocess():
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "from goldlabel.settings import settings; print(settings.root)",
        ],
        env={"PATH": ""},
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == ".goldlabel"


def test_assignment_changes_resolve_on_next_call():
    assert resolve(None, "gold.json") == Path(".goldlabel/gold.json")
    settings.root = Path("/elsewhere")
    assert resolve(None, "gold.json") == Path("/elsewhere/gold.json")


def test_explicit_path_beats_setting_beats_default(monkeypatch):
    settings.root = Path("/setting")
    assert resolve(Path("/mine/x.jsonl"), "gold.json") == Path("/mine/x.jsonl")
    assert resolve(None, "gold.json") == Path("/setting/gold.json")
    settings.root = Path(".goldlabel")
    assert resolve(None, "gold.json") == Path(".goldlabel/gold.json")


def test_reset_fixture_restores_default_and_clears_env():
    import os

    assert settings.root == Path(".goldlabel")
    assert "GOLDLABEL_DIR" not in os.environ


def test_env_var_is_deleted_for_each_test(monkeypatch):
    monkeypatch.setenv("GOLDLABEL_DIR", "/leak")
    settings.root = Path("/leak")


def test_previous_test_did_not_leak():
    import os

    assert settings.root == Path(".goldlabel")
    assert "GOLDLABEL_DIR" not in os.environ


def test_import_writes_nothing_and_reads_only_goldlabel_dir(tmp_path):
    work = tmp_path / "cwd"
    work.mkdir()
    script = (
        "import os\n"
        "reads = []\n"
        "class Env(dict):\n"
        "    def get(self, k, d=None):\n"
        "        reads.append(k); return super().get(k, d)\n"
        "    def __getitem__(self, k):\n"
        "        reads.append(k); return super().__getitem__(k)\n"
        "    def __contains__(self, k):\n"
        "        reads.append(k); return super().__contains__(k)\n"
        "os.environ.get = Env(os.environ).get\n"
        "import goldlabel.settings\n"
        "print(sorted(set(reads)))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", script],
        cwd=work,
        env={"PATH": "", "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        capture_output=True,
        text=True,
        check=True,
    )
    # importing the submodule imports the package, whose dependencies read their own variables
    reads = ast.literal_eval(out.stdout.strip())
    assert [r for r in reads if r.startswith("GOLDLABEL")] in (["GOLDLABEL_DIR"], [])
    assert list(work.iterdir()) == []


def test_ignore_creates_appends_and_is_idempotent(tmp_path):
    from goldlabel.settings import ignore

    folder = tmp_path / "f"
    ignore(folder, "a")
    ignore(folder, "a")
    assert (folder / ".gitignore").read_text() == "a\n"
    (folder / ".gitignore").write_text("mine")  # a user's file, no trailing newline
    ignore(folder, "a")
    ignore(folder, "b")
    assert (folder / ".gitignore").read_text() == "mine\na\nb\n"


def test_git_ignores_the_cache_and_the_lock_but_not_the_record(tmp_path):
    from pydantic_ai.usage import RequestUsage

    from goldlabel._label import _acquire
    from goldlabel.cost import cache_put

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    root = tmp_path / ".goldlabel"
    cache_put(root / "cache", "k", {"x": 1}, RequestUsage(input_tokens=1))
    _acquire(root / "labelling.lock", 1234)
    (root / "gold.json").write_text("{}")
    out = subprocess.run(
        ["git", "-C", str(tmp_path), "status", "--porcelain", "-uall"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.split() == ["??", ".goldlabel/.gitignore", "??", ".goldlabel/gold.json"]

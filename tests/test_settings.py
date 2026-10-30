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
    assert resolve(None, "gold.jsonl") == Path(".goldlabel/gold.jsonl")
    settings.root = Path("/elsewhere")
    assert resolve(None, "gold.jsonl") == Path("/elsewhere/gold.jsonl")


def test_explicit_path_beats_setting_beats_default(monkeypatch):
    settings.root = Path("/setting")
    assert resolve(Path("/mine/x.jsonl"), "gold.jsonl") == Path("/mine/x.jsonl")
    assert resolve(None, "gold.jsonl") == Path("/setting/gold.jsonl")
    settings.root = Path(".goldlabel")
    assert resolve(None, "gold.jsonl") == Path(".goldlabel/gold.jsonl")


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


def test_the_old_environment_variable_is_not_read():
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "from goldlabel.settings import settings; print(settings.root)",
        ],
        env={"HUNCHES_DIR": "/some/where", "PATH": ""},
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == ".goldlabel"

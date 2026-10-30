"""009/T005: `goldlabel install`. A scratch project and a fake home; no network, no real agent."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from goldlabel import GOLD_RULE_FULL
from goldlabel.cli import main, steering_text

ROOT = Path(__file__).resolve().parent.parent
SKILLS = sorted(p.name for p in (ROOT / "src/goldlabel/skills").iterdir() if p.is_dir())


@pytest.fixture
def env(tmp_path, monkeypatch):
    proj, home = tmp_path / "proj", tmp_path / "home"
    proj.mkdir()
    home.mkdir()
    monkeypatch.chdir(proj)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return proj, home


def run(capsys, *argv):
    try:
        code = main(list(argv))
    except SystemExit as e:  # argparse usage errors
        code = e.code
    out = capsys.readouterr()
    return code, out.out, out.err


def tree(root: Path):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_there_is_a_skill_per_stage():
    assert "goldlabel" in SKILLS


@pytest.mark.parametrize(
    "agent, folder",
    [
        ("claude", ".claude/skills"),
        ("codex", ".agents/skills"),
        ("copilot", ".agents/skills"),
        ("kiro", ".kiro/skills"),
    ],
)
def test_project_install_writes_every_skill_where_the_agent_reads_it(
    env, capsys, agent, folder
):
    proj, _ = env
    code, out, _ = run(capsys, "install", agent)
    assert code == 0
    for name in SKILLS:
        assert (proj / folder / name / "SKILL.md").is_file()
        assert f"{folder}/{name}" in out
    assert tree(proj / folder / "goldlabel") == tree(
        ROOT / "src/goldlabel/skills/goldlabel"
    )  # the references travel with it
    assert not list(proj.rglob("*.tmp")) and not list(proj.rglob(".*.tmp"))


def test_global_install_goes_under_the_home_directory(env, capsys):
    proj, home = env
    code, _, _ = run(capsys, "install", "claude", "codex", "kiro", "--global")
    assert code == 0
    for folder in (".claude/skills", ".agents/skills", ".kiro/skills"):
        assert (home / folder / "goldlabel" / "SKILL.md").is_file()
    assert (home / ".kiro/steering/goldlabel.md").read_text() == steering_text()
    assert not any(proj.iterdir())


def test_codex_and_copilot_share_one_folder_written_once(env, capsys):
    proj, _ = env
    code, out, _ = run(capsys, "install", "codex", "copilot")
    assert code == 0
    assert out.count(".agents/skills/goldlabel ") == 1
    assert "codex and copilot" in out
    assert [p.name for p in proj.iterdir()] == [".agents"]


def test_kiro_gets_the_steering_file_and_the_custom_agent_note(env, capsys):
    proj, _ = env
    _, out, _ = run(capsys, "install", "kiro")
    steering = proj / ".kiro/steering/goldlabel.md"
    assert steering.read_text() == steering_text()
    assert GOLD_RULE_FULL in steering.read_text()
    assert "skill://.kiro/skills/*/SKILL.md" in out and "resources" in out
    assert not (proj / ".kiro/agents").exists()  # never edits the user's agents


def test_the_repos_own_steering_file_is_what_the_installer_writes():
    assert (ROOT / ".kiro/steering/goldlabel.md").read_text() == steering_text()


def test_next_steps_are_printed_per_agent(env, capsys):
    _, out, _ = run(capsys, "install", "all")
    assert "/skills reload" in out  # copilot
    assert "restart" in out  # codex and claude


def test_second_run_changes_nothing_and_says_so(env, capsys):
    proj, _ = env
    run(capsys, "install", "all")
    mtimes = {p: p.stat().st_mtime_ns for p in proj.rglob("*") if p.is_file()}
    code, out, _ = run(capsys, "install", "all")
    assert code == 0 and "written" not in out and "up to date" in out
    assert mtimes == {p: p.stat().st_mtime_ns for p in proj.rglob("*") if p.is_file()}


def test_a_changed_skill_is_refused_until_force(env, capsys):
    proj, _ = env
    run(capsys, "install", "claude")
    skill = proj / ".claude/skills/goldlabel/SKILL.md"
    skill.write_text("mine")
    code, out, _ = run(capsys, "install", "claude")
    assert code == 1 and "differs" in out and "--force" in out
    assert skill.read_text() == "mine"
    code, out, _ = run(capsys, "install", "claude", "--force")
    assert code == 0
    assert (
        skill.read_text()
        == (ROOT / "src/goldlabel/skills/goldlabel/SKILL.md").read_text()
    )


def test_dry_run_writes_nothing(env, capsys):
    proj, _ = env
    code, out, _ = run(capsys, "install", "all", "--dry-run")
    assert code == 0 and "would write" in out
    assert not any(proj.iterdir())


def test_dir_target_for_any_other_agent(env, capsys, tmp_path):
    out_dir = tmp_path / "elsewhere"
    code, out, _ = run(capsys, "install", "--dir", str(out_dir))
    assert code == 0
    assert sorted(p.name for p in out_dir.iterdir()) == SKILLS
    assert "point your agent" in out
    code, _, _ = run(capsys, "install", "claude", "--dir", str(out_dir))
    assert code == 2


def test_unknown_agent_lists_the_valid_names_and_writes_nothing(env, capsys):
    proj, _ = env
    code, out, err = run(capsys, "install", "cursor")
    assert code == 1 and not any(proj.iterdir())
    for name in ("claude", "codex", "copilot", "kiro", "all"):
        assert name in out + err


def test_no_agent_is_a_usage_error(env, capsys):
    code, _, err = run(capsys, "install")
    assert code == 2 and "claude" in err


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
def test_a_symlinked_skills_folder_is_refused(env, capsys, tmp_path):
    proj, _ = env
    (tmp_path / "real").mkdir()
    (proj / ".claude").mkdir()
    (proj / ".claude/skills").symlink_to(tmp_path / "real")
    code, out, err = run(capsys, "install", "claude")
    assert code == 1 and "symlink" in out + err
    assert not any((tmp_path / "real").iterdir())


def test_a_failure_while_writing_leaves_no_half_written_folder(
    env, capsys, monkeypatch
):
    proj, _ = env

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    code, out, err = run(capsys, "install", "claude")
    assert code == 1 and "disk full" in out + err
    leftovers = [p for p in proj.rglob("*") if p.is_file() or p.name.endswith(".tmp")]
    assert leftovers == []


def test_the_installer_never_touches_gold_or_the_network():
    src = (ROOT / "src/goldlabel/cli.py").read_text()
    for word in ("goldlabel.gold", "Gold", "socket", "urllib", "http", "subprocess"):
        assert word not in src, word


def test_importing_goldlabel_does_not_import_the_cli():
    code = "import sys, goldlabel; assert 'goldlabel.cli' not in sys.modules"
    r = subprocess.run(
        [sys.executable, "-c", code],
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.pathsep.join(sys.path),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_the_wheel_ships_the_cli_and_the_console_script(tmp_path):
    subprocess.run(
        ["uv", "build", "--wheel", "-o", str(tmp_path), str(ROOT)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    (wheel,) = tmp_path.glob("goldlabel-*.whl")
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        entry = next(n for n in names if n.endswith("entry_points.txt"))
        assert "goldlabel = goldlabel.cli:main" in z.read(entry).decode()
    assert "goldlabel/cli.py" in names

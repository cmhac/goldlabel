import importlib
import os
import subprocess
import sys
import tomllib
from pathlib import Path

PUBLIC = [
    "S3Corpus",
    "PgCorpus",
    "Table",
    "read_seeds",
    "search",
    "asearch",
    "Candidates",
    "Taxonomy",
    "Classifier",
    "Predictions",
    "Estimate",
    "CostLimit",
    "Gold",
    "GoldSet",
    "evaluate",
    "aevaluate",
    "Evaluation",
    "eval_log",
    "EvalLog",
    "band_sample",
    "BandReport",
    "cost",
    "Cost",
    "settings",
    "label",
    "GOLD_RULE_SHORT",
    "GOLD_RULE_FULL",
    "GoldError",
    "__version__",
]


def run(code, cwd):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join(sys.path),
    }
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_all_is_exactly_the_public_list():
    import hunches

    assert sorted(hunches.__all__) == sorted(PUBLIC)
    for name in PUBLIC:
        assert hasattr(hunches, name), name


def test_version_is_the_package_metadata():
    from importlib.metadata import version

    import hunches

    assert hunches.__version__ == version("hunches")


def test_import_loads_no_tui_keyring_dotenv_or_optional_backends(tmp_path):
    code = (
        "import sys, hunches\n"
        "hunches.Classifier; hunches.PgCorpus; hunches.S3Corpus\n"
        "bad = {'textual','keyring','platformdirs','dotenv','boto3','psycopg','polars','pandas'}\n"
        "found = sorted(bad & {m.split('.')[0] for m in sys.modules})\n"
        "assert not found, found\n"
    )
    result = run(code, tmp_path)
    assert result.returncode == 0, result.stderr


def test_import_has_no_side_effects(tmp_path):
    code = (
        "import os\n"
        "before = dict(os.environ)\n"
        "import hunches\n"
        "assert dict(os.environ) == before\n"
    )
    result = run(code, tmp_path)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_import_with_a_read_only_hunches_dir_changes_nothing(tmp_path):
    (tmp_path / ".hunches").mkdir()
    (tmp_path / ".hunches" / "gold.jsonl").write_text("{}\n")
    (tmp_path / ".hunches").chmod(0o555)
    try:
        result = run("import hunches", tmp_path)
        assert result.returncode == 0, result.stderr
        assert sorted(p.name for p in tmp_path.rglob("*")) == [
            ".hunches",
            "gold.jsonl",
        ]
    finally:
        (tmp_path / ".hunches").chmod(0o755)


def test_name_shadowing_the_package_attributes_is_the_documented_one():
    import hunches
    from hunches.settings import Settings, resolve

    assert isinstance(hunches.settings, Settings)  # the object, not the submodule
    assert hunches.settings.root == Path(".hunches")
    assert callable(hunches.cost) and hunches.cost.__module__ == "hunches.cost"
    assert callable(hunches.search) and hunches.search.__module__ == (
        "hunches.candidates"
    )
    assert resolve(None, "gold.jsonl") == hunches.settings.root / "gold.jsonl"
    assert importlib.import_module("hunches.settings").resolve is resolve
    assert hasattr(importlib.import_module("hunches.cost"), "cache_key")


def test_dependencies_dropped():
    deps = tomllib.loads(Path("pyproject.toml").read_text())["project"]["dependencies"]
    names = {d.split(">")[0].split("[")[0].strip().lower() for d in deps}
    assert not names & {"keyring", "platformdirs", "python-dotenv"}

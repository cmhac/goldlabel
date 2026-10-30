import importlib
import inspect
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
    "get_candidates",
    "aget_candidates",
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
    import goldlabel

    assert sorted(goldlabel.__all__) == sorted(PUBLIC)
    for name in PUBLIC:
        assert hasattr(goldlabel, name), name


def test_version_is_the_package_metadata():
    from importlib.metadata import version

    import goldlabel

    assert goldlabel.__version__ == version("goldlabel")


def test_import_loads_no_tui_keyring_dotenv_or_optional_backends(tmp_path):
    code = (
        "import sys, goldlabel\n"
        "goldlabel.Classifier; goldlabel.PgCorpus; goldlabel.S3Corpus\n"
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
        "import goldlabel\n"
        "assert dict(os.environ) == before\n"
    )
    result = run(code, tmp_path)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_import_with_a_read_only_goldlabel_dir_changes_nothing(tmp_path):
    (tmp_path / ".goldlabel").mkdir()
    (tmp_path / ".goldlabel" / "gold.jsonl").write_text("{}\n")
    (tmp_path / ".goldlabel").chmod(0o555)
    try:
        result = run("import goldlabel", tmp_path)
        assert result.returncode == 0, result.stderr
        assert sorted(p.name for p in tmp_path.rglob("*")) == [
            ".goldlabel",
            "gold.jsonl",
        ]
    finally:
        (tmp_path / ".goldlabel").chmod(0o755)


def test_name_shadowing_the_package_attributes_is_the_documented_one():
    import goldlabel
    from goldlabel.settings import Settings, resolve

    assert isinstance(goldlabel.settings, Settings)  # the object, not the submodule
    assert goldlabel.settings.root == Path(".goldlabel")
    assert callable(goldlabel.cost) and goldlabel.cost.__module__ == "goldlabel.cost"
    assert inspect.ismodule(
        goldlabel.search
    )  # only cost and settings shadow submodules
    assert resolve(None, "gold.jsonl") == goldlabel.settings.root / "gold.jsonl"
    assert importlib.import_module("goldlabel.settings").resolve is resolve
    assert hasattr(importlib.import_module("goldlabel.cost"), "cache_key")


def test_dependencies_dropped():
    deps = tomllib.loads(Path("pyproject.toml").read_text())["project"]["dependencies"]
    names = {d.split(">")[0].split("[")[0].strip().lower() for d in deps}
    assert not names & {"keyring", "platformdirs", "python-dotenv"}

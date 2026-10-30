import importlib.util
import json
import re
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location(
    "sync_versions", ROOT / "scripts/sync_versions.py"
)
assert spec and spec.loader
sync_versions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_versions)


def manifest_versions(root: Path) -> dict[str, str]:
    plugin = json.loads((root / "plugin.json").read_text())
    claude = json.loads((root / ".claude-plugin/plugin.json").read_text())
    market = json.loads((root / ".claude-plugin/marketplace.json").read_text())
    return {
        "plugin.json": plugin["version"],
        ".claude-plugin/plugin.json": claude["version"],
        ".claude-plugin/marketplace.json": market["plugins"][0]["version"],
    }


def test_manifest_versions_match_pyproject():
    # The publish workflow runs this before it tags: fix with `uv run python scripts/sync_versions.py`.
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert manifest_versions(ROOT) == dict.fromkeys(sync_versions.MANIFESTS, version)


def test_sync_rewrites_only_the_version(tmp_path):
    for name in ["pyproject.toml", *sync_versions.MANIFESTS]:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, tmp_path / name)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        re.sub(r'(?m)^version = ".*"$', 'version = "9.8.7"', pyproject.read_text())
    )
    before = {n: (tmp_path / n).read_text() for n in sync_versions.MANIFESTS}

    assert sync_versions.sync(tmp_path) == sync_versions.MANIFESTS
    assert manifest_versions(tmp_path) == dict.fromkeys(
        sync_versions.MANIFESTS, "9.8.7"
    )
    for name, text in before.items():
        old = manifest_versions(ROOT)[name]
        assert (tmp_path / name).read_text() == text.replace(f'"{old}"', '"9.8.7"')
    assert sync_versions.sync(tmp_path) == []

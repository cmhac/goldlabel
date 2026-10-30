"""Copy the version in pyproject.toml into the plugin manifests (run by pre-commit)."""

import re
import sys
import tomllib
from pathlib import Path

MANIFESTS = [
    "plugin.json",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
]
VERSION = re.compile(r'("version":\s*")[^"]*(")')


def sync(root: Path) -> list[str]:
    """Write the pyproject version into each manifest; return the ones changed."""
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    changed = []
    for name in MANIFESTS:
        path = root / name
        text = path.read_text()
        # Edit the string in place so the file's formatting is kept.
        new, n = VERSION.subn(rf"\g<1>{version}\g<2>", text)
        if n != 1:
            sys.exit(f"{name}: expected one version key, found {n}")
        if new != text:
            path.write_text(new)
            changed.append(name)
    return changed


if __name__ == "__main__":
    for name in sync(Path(__file__).resolve().parent.parent):
        print(f"updated {name}")

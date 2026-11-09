import os
from pathlib import Path


class Settings:
    """Process-wide settings. Assign `settings.root` to change where artifacts go."""

    def __init__(self):
        self.root = Path(os.environ.get("GOLDLABEL_DIR") or ".goldlabel")


settings = Settings()


def resolve(path, default_name):
    """A path argument beats `settings.root` beats the default; nothing is created."""
    return Path(path) if path is not None else settings.root / default_name


def ignore(folder, line):
    """Make sure `folder/.gitignore` has `line`: created if missing, appended to (never rewritten) if not."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ".gitignore"
    have = path.read_text().splitlines() if path.exists() else []
    if line not in have:
        with path.open("a") as f:
            f.write(
                ("\n" if have and not path.read_text().endswith("\n") else "")
                + line
                + "\n"
            )

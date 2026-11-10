"""Where goldlabel keeps its files: the storage folder, `goldlabel.settings.root`."""

import os
from pathlib import Path


class Settings:
    """Process-wide settings; use the ready-made `goldlabel.settings` object.

    Attributes:
        root: The storage folder (a `Path`) for the candidate list, the gold files, the
            evaluation log and the cache. It starts as the `GOLDLABEL_DIR` environment variable,
            or `.goldlabel` in the working directory when that is not set. Assign to it to
            change where files go.
    """

    def __init__(self):
        self.root = Path(os.environ.get("GOLDLABEL_DIR") or ".goldlabel")


settings = Settings()


def resolve(path, default_name):
    """Choose where a file goes: a path argument beats `settings.root` beats the default name.

    Returns:
        Path: The path to use; nothing is created.
    """
    return Path(path) if path is not None else settings.root / default_name


def ignore(folder, line):
    """Make sure `folder/.gitignore` has `line`: created if missing, appended to (never rewritten) if not.

    Creates the folder if needed.
    """
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

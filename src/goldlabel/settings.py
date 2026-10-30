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

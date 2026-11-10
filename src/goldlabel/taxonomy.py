"""The taxonomy: the labels an item can get, and whether it gets one label or several."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from goldlabel import _html

OFF_TOPIC = "off_topic"


class Label(BaseModel):
    """One label: a short `name` and a `description` the model reads to decide when it applies."""

    name: str
    description: str = ""


class Taxonomy(BaseModel):
    """The labels an item can get, and whether it gets one label or several.

    Build one with the labels as a dict of name to description:
    `Taxonomy(mode="single", labels={"burnout": "The author is worn out by their work."})`.
    It cannot be changed after it is made. The label `off_topic` ("the item matches none of the
    labels") is built in: it is always available to the model and to people labelling, and you
    must not list it yourself.

    Attributes:
        mode: "single" (each item gets exactly one label) or "multi" (each item gets every label
            that applies).
        labels: The labels you define, each with a name and a description.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["single", "multi"]
    labels: list[Label]

    @field_validator("labels", mode="before")
    @classmethod
    def _from_dict(cls, labels):
        if isinstance(labels, dict):
            return [Label(name=n, description=d) for n, d in labels.items()]
        return labels

    @field_validator("labels")
    @classmethod
    def _no_off_topic(cls, labels: list[Label]) -> list[Label]:
        if any(label.name == OFF_TOPIC for label in labels):
            raise ValueError(f"'{OFF_TOPIC}' is built in; do not list it")
        return labels

    @property
    def names(self) -> list[str]:
        """The names of all labels: yours, in order, then `off_topic`."""
        return all_labels(self)

    def _repr_html_(self) -> str:
        rows = [(label.name, label.description) for label in self.labels]
        rows.append((OFF_TOPIC, "the item matches none of the labels above"))
        return _html.line(f"Taxonomy ({self.mode}-label)") + _html.table(
            ["label", "description"], rows
        )

    @classmethod
    def read(cls, path) -> "Taxonomy":
        """Load a taxonomy from a YAML file written by `write`.

        Args:
            path: The YAML file.

        Returns:
            Taxonomy: The mode and labels in the file.
        """
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))

    def write(self, path) -> None:
        """Save the taxonomy as a YAML file that `Taxonomy.read` can load.

        An existing file at `path` is overwritten and missing folders are created.

        Args:
            path: The YAML file to write.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.model_dump(), sort_keys=False))


def all_labels(taxonomy: Taxonomy) -> list[str]:
    """List every label of the taxonomy, including `off_topic`.

    Returns:
        list[str]: The label names, `off_topic` last.
    """
    return [label.name for label in taxonomy.labels] + [OFF_TOPIC]


def validate_labels(labels: list[str], taxonomy: Taxonomy) -> None:
    """Check a list of labels against the taxonomy's rules (for gold and predicted labels alike).

    Args:
        labels: The labels given to one item.
        taxonomy: The taxonomy they must follow.

    Raises:
        ValueError: The list is empty, uses a label not in the taxonomy, combines `off_topic`
            with another label, or has other than exactly one label in single mode.
    """
    if not labels:
        raise ValueError("at least one label is required")
    unknown = set(labels) - set(all_labels(taxonomy))
    if unknown:
        raise ValueError(f"unknown labels: {sorted(unknown)}")
    if OFF_TOPIC in labels and len(set(labels)) > 1:
        raise ValueError(f"'{OFF_TOPIC}' must be the only label")
    if taxonomy.mode == "single" and len(labels) != 1:
        raise ValueError("single mode requires exactly one label")

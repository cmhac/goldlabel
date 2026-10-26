from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from hunches import _html

OFF_TOPIC = "off_topic"


class Label(BaseModel):
    name: str
    description: str = ""


class Taxonomy(BaseModel):
    """`labels` are the labels you define; `off_topic` is built in and listed by `names`."""

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
        return all_labels(self)

    def _repr_html_(self) -> str:
        rows = [(label.name, label.description) for label in self.labels]
        rows.append((OFF_TOPIC, "the item matches none of the labels above"))
        return _html.line(f"Taxonomy ({self.mode}-label)") + _html.table(
            ["label", "description"], rows
        )

    @classmethod
    def read(cls, path) -> "Taxonomy":
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))

    def write(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.model_dump(), sort_keys=False))


def all_labels(taxonomy: Taxonomy) -> list[str]:
    return [label.name for label in taxonomy.labels] + [OFF_TOPIC]


def validate_labels(labels: list[str], taxonomy: Taxonomy) -> None:
    """Raise ValueError unless labels obey the spec rules (gold and predicted alike)."""
    if not labels:
        raise ValueError("at least one label is required")
    unknown = set(labels) - set(all_labels(taxonomy))
    if unknown:
        raise ValueError(f"unknown labels: {sorted(unknown)}")
    if OFF_TOPIC in labels and len(set(labels)) > 1:
        raise ValueError(f"'{OFF_TOPIC}' must be the only label")
    if taxonomy.mode == "single" and len(labels) != 1:
        raise ValueError("single mode requires exactly one label")

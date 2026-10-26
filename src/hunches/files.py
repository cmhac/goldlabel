import hashlib
import json
import tomllib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

from hunches.taxonomy import Taxonomy

SAMPLE_SIZE = 50  # gold rows per split (spec stages 4 and 6)


class Config(BaseModel):
    backend: Literal["local", "s3", "pgvector"] = "local"
    corpus_dir: str | None = (
        None  # local backend: dir with vectors.npy, items.jsonl, meta.json
    )
    s3_bucket: str | None = None
    s3_index: str | None = None
    embedding_model: str = ""
    s3_region: str | None = None  # None: boto3's default resolution
    # pgvector backend: None is stored as absent; read through pg_setting() for the defaults
    pg_table: str | None = None
    pg_id_column: str | None = None
    pg_text_column: str | None = None
    pg_vector_column: str | None = None
    # two-table layout: the text lives in pg_text_table, joined on pg_text_id_column = pg_id_column
    pg_text_table: str | None = None
    pg_text_id_column: str | None = None  # None: the same name as pg_id_column
    pg_url_var: str | None = None  # an explicit name; the form sets pg_url_id instead
    pg_url_id: str | None = None  # search.pg_url_id of the URL: names its keyring entry
    pg_search: Literal["exact", "index"] | None = None
    pg_statement_timeout_s: int | None = None
    pg_auth: Literal["url", "rds_iam"] | None = None
    pg_aws_region: str | None = None
    pg_aws_profile: str | None = None
    classifier_model: str
    target_metric: Literal["accuracy", "macro_f1", "micro_f1", "exact_match"] = (
        "accuracy"
    )
    target_score: float = 0.90

    @model_validator(mode="before")
    @classmethod
    def _old_keys(cls, data):
        # 001 wrote cheap_model; a new key wins over an old one
        if isinstance(data, dict) and "cheap_model" in data:
            data = dict(data)
            data.setdefault("classifier_model", data.pop("cheap_model"))
        return data


PG_DEFAULTS = {
    "pg_id_column": "id",
    "pg_text_column": "text",
    "pg_vector_column": "embedding",
    "pg_url_var": "HUNCHES_PG_URL",
    "pg_search": "exact",
    "pg_auth": "url",
}  # fields not listed (table, timeout, region, profile) have no default: None


def pg_setting(config: Config, name: str):
    """A pg_* config field with its default applied (a stored 0 stays 0)."""
    value = getattr(config, name)
    return PG_DEFAULTS.get(name) if value is None else value


def root() -> Path:
    return Path(".hunches")


def ensure_root() -> Path:
    root().mkdir(exist_ok=True)
    return root()


def read_text(name: str) -> str | None:
    """Read a text file in .hunches/ (seeds.csv, brief.md, prompt.md, ...); None if missing."""
    path = root() / name
    return path.read_text() if path.exists() else None


def write_text(name: str, text: str) -> None:
    ensure_root()
    (root() / name).write_text(text)


def read_config(project: Path | None = None) -> Config:
    """Read config.toml of `project` (default: the current directory's project)."""
    path = (project / ".hunches" if project else root()) / "config.toml"
    return Config.model_validate(tomllib.loads(path.read_text()))


def write_config(config: Config, project: Path | None = None) -> None:
    # json.dumps output is a valid TOML basic string / number / bool for our value types
    lines = [
        f"{k} = {json.dumps(v)}"
        for k, v in config.model_dump().items()
        if v is not None
    ]
    text = "\n".join(lines) + "\n"
    if project:  # another project's config: never chdir to it
        (project / ".hunches" / "config.toml").write_text(text)
    else:
        write_text("config.toml", text)


def _sha(data) -> str:
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def _config() -> Config | None:
    try:
        return read_config()
    except (OSError, ValueError):  # no config.toml yet (tests, a project being created)
        return None


def _taxonomy() -> Taxonomy | None:
    try:
        return read_taxonomy()
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        return None


def run_digest(prompt: str, taxonomy: Taxonomy, model: str) -> str:
    """What the classifier cache key hashes minus the item text: equal digests mean cache hits."""
    from hunches import classifier  # classifier imports this module

    return _sha([model, classifier.system_prompt(prompt, taxonomy)])


def current_run() -> str | None:
    """run_digest of the project as it is now; None while there is no taxonomy or config."""
    config, taxonomy = _config(), _taxonomy()
    if config is None or taxonomy is None:
        return None
    return run_digest(read_text("prompt.md") or "", taxonomy, config.classifier_model)


def read_jsonl(name: str) -> list[dict]:
    path = root() / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(name: str, rows: list[dict]) -> None:
    write_text(name, "".join(json.dumps(r) + "\n" for r in rows))


def append_jsonl(name: str, row: dict) -> None:
    ensure_root()
    with (root() / name).open("a") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()


def read_taxonomy() -> Taxonomy:
    return Taxonomy.read(root() / "taxonomy.yaml")


def write_taxonomy(taxonomy: Taxonomy) -> None:
    taxonomy.write(ensure_root() / "taxonomy.yaml")

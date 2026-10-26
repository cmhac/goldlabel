"""Content analysis over an already-embedded corpus, as a library.

Importing reads, writes and networks nothing. Two exported names shadow submodules of the package
(`hunches.cost` is the function, `hunches.settings` the object): inside the package and in tests
import by name, `from hunches.cost import cache_key`, `from hunches.settings import resolve`.
"""

from importlib.metadata import PackageNotFoundError, version

from hunches.candidates import Candidates, asearch, read_seeds, search
from hunches.classifier import Classifier, CostLimit, Estimate, Predictions
from hunches.cost import Cost, cost
from hunches.evaluation import (
    BandReport,
    EvalLog,
    Evaluation,
    aevaluate,
    band_sample,
    eval_log,
    evaluate,
)
from hunches.gold import Gold, GoldSet
from hunches.search import LocalCorpus, PgCorpus, S3Corpus
from hunches.settings import settings
from hunches.taxonomy import Taxonomy

try:
    __version__ = version("hunches")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"

__all__ = [
    "BandReport",
    "Candidates",
    "Classifier",
    "Cost",
    "CostLimit",
    "Estimate",
    "EvalLog",
    "Evaluation",
    "Gold",
    "GoldSet",
    "LocalCorpus",
    "PgCorpus",
    "Predictions",
    "S3Corpus",
    "Taxonomy",
    "__version__",
    "aevaluate",
    "asearch",
    "band_sample",
    "cost",
    "eval_log",
    "evaluate",
    "read_seeds",
    "search",
    "settings",
]

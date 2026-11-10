"""Content analysis over a corpus (seeds, keywords or the whole corpus, then an LLM classifier), as a library.

Importing reads, writes and networks nothing. Two exported names shadow submodules of the package
(`goldlabel.cost` is the function, `goldlabel.settings` the object): inside the package and in tests
import by name, `from goldlabel.cost import cache_key`, `from goldlabel.settings import resolve`.

Every public function and class explains itself: hover over a name in your editor, run
`help(gl.Classifier)` or `help(gl.Classifier.with_prompt)`, or type `gl.Classifier?` in a notebook.
"""

from importlib.metadata import PackageNotFoundError, version

from goldlabel._gold_rule import GOLD_RULE_FULL, GOLD_RULE_SHORT, GoldError
from goldlabel._label import label
from goldlabel.candidates import (
    Candidates,
    aget_candidates,
    get_candidates,
    read_seeds,
)
from goldlabel.classifier import Classifier, CostLimit, Estimate, Predictions
from goldlabel.cost import Cost, cost
from goldlabel.evaluation import BandReport, Evaluation
from goldlabel.gold import Gold, GoldSet, Sample
from goldlabel.search import PgCorpus, S3Corpus, Table
from goldlabel.settings import settings
from goldlabel.taxonomy import Taxonomy

try:
    __version__ = version("goldlabel")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"

__all__ = [
    "GOLD_RULE_FULL",
    "GOLD_RULE_SHORT",
    "BandReport",
    "Candidates",
    "Classifier",
    "Cost",
    "CostLimit",
    "Estimate",
    "Evaluation",
    "Gold",
    "GoldError",
    "GoldSet",
    "PgCorpus",
    "Predictions",
    "S3Corpus",
    "Sample",
    "Table",
    "Taxonomy",
    "__version__",
    "aget_candidates",
    "cost",
    "get_candidates",
    "label",
    "read_seeds",
    "settings",
]

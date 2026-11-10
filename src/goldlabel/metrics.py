"""Scores for a classifier compared with gold labels: precision, recall, F1 and exact match."""

from dataclasses import dataclass

from goldlabel.taxonomy import Taxonomy


@dataclass
class LabelMetrics:
    """How well one label was predicted.

    Attributes:
        precision: Of the items predicted with the label, the share that really have it.
        recall: Of the items that really have the label, the share that were predicted with it.
        f1: The combination of precision and recall (0 when both are 0).
        tp: Items correctly predicted with the label.
        fp: Items predicted with the label that do not have it.
        fn: Items that have the label but were not predicted with it.
        gold_count: Items whose gold labels include this label.
        predicted_count: Items predicted with this label.
    """

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    gold_count: int  # items whose gold set contains the label
    predicted_count: int


@dataclass
class Metrics:
    """All the scores of one evaluation.

    Attributes:
        exact_match: The share of items whose predicted labels equal the gold labels (plain
            accuracy for a single-label taxonomy).
        per_label: Each label's `LabelMetrics`.
        macro_f1: The average F1 over the labels that appear in the gold labels or the predictions.
        micro_f1: F1 counted over all items and labels together.
        disagreements: The positions of the items where prediction and gold differ.
        n: How many items were scored.
    """

    exact_match: float  # predicted set == gold set (plain accuracy in single mode)
    per_label: dict[str, LabelMetrics]
    macro_f1: float
    micro_f1: float
    disagreements: list[int]  # indices where predicted != gold
    n: int


def _ratio(num: float, den: float) -> float:
    # every ratio with a zero denominator is defined as 0
    return num / den if den else 0.0


def compute_metrics(
    gold: list[set[str]], predicted: list[set[str]], labels: list[str]
) -> Metrics:
    """Score predictions. `labels` is the full list including off_topic.

    Macro-F1 averages per-label F1 over labels that appear in gold or in the
    predictions; a label absent from both is undefined, not a zero.

    Returns:
        Metrics: The scores; every ratio with a zero denominator is 0.
    """
    per_label = {}
    for label in labels:
        tp = sum(label in g and label in p for g, p in zip(gold, predicted))
        fp = sum(label not in g and label in p for g, p in zip(gold, predicted))
        fn = sum(label in g and label not in p for g, p in zip(gold, predicted))
        precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
        per_label[label] = LabelMetrics(
            precision=precision,
            recall=recall,
            f1=_ratio(2 * precision * recall, precision + recall),
            tp=tp,
            fp=fp,
            fn=fn,
            gold_count=tp + fn,
            predicted_count=tp + fp,
        )
    disagreements = [i for i, (g, p) in enumerate(zip(gold, predicted)) if g != p]
    present = [m for m in per_label.values() if m.gold_count or m.predicted_count]
    tp, fp, fn = (
        sum(getattr(m, k) for m in per_label.values()) for k in ("tp", "fp", "fn")
    )
    return Metrics(
        exact_match=_ratio(len(gold) - len(disagreements), len(gold)),
        per_label=per_label,
        macro_f1=_ratio(sum(m.f1 for m in present), len(present)),
        micro_f1=_ratio(2 * tp, 2 * tp + fp + fn),
        disagreements=disagreements,
        n=len(gold),
    )


def target_value(metrics: Metrics, name: str) -> float:
    """Pick one score out of `metrics` by name.

    `accuracy` and `exact_match` are the same number; the UI label differs by mode.

    Returns:
        float: The score named: "accuracy", "exact_match", "macro_f1" or "micro_f1".
    """
    return {
        "accuracy": metrics.exact_match,
        "exact_match": metrics.exact_match,
        "macro_f1": metrics.macro_f1,
        "micro_f1": metrics.micro_f1,
    }[name]


def default_target_metric(taxonomy: Taxonomy) -> str:
    """Choose the headline score when the user has not: accuracy (single), macro_f1 (multi).

    Returns:
        str: The metric name.
    """
    return "accuracy" if taxonomy.mode == "single" else "macro_f1"

# Reusing a finished classifier

Do this when the user says the classifier is final. It is for notebooks and automated pipelines alike; neither needs the gold file.

## Save a bundle

```python
final = hn.evaluate(clf, gold.test)  # the one reported number; see tuning.md
clf.save("classifiers/scams/", evaluation=final)
```

The folder holds `classifier.yaml` (the model), `taxonomy.yaml`, `prompt.md` and `evaluation.json` (the metrics, split, n, date and the classifier's digest). Ask the user where in the repository it should live; a shared folder like `classifiers/<name>/` is the usual choice. The cache location is not part of the bundle. Tell the user to commit the folder.

## Use it in a pipeline

```python
import hunches as hn

clf = hn.Classifier.load(
    "classifiers/scams/"
)  # warns if prompt/model no longer match the recorded evaluation
results = clf.classify(new_items, out="out/results.jsonl", max_cost=2.00)
```

`new_items` is a list of strings, or of dicts with `id` and `text` (other keys are carried through to the result rows), or any result object with `.rows`. A pipeline must name its `out=`; re-running resumes. Pass `Classifier.load(dir, cache="path")` to choose the cache directory.

Estimate and `max_cost` apply here too: do not start a large run for the user without showing `clf.estimate(new_items)` and getting a yes.

If the `UserWarning` about the digest appears, the bundle's model or prompt was edited after it was evaluated. Do not silence it; tell the user the recorded evaluation no longer describes this classifier, and offer to re-evaluate on a fresh, human-labelled split.

## A classifier declared in code

A shared module works as well as a bundle:

```python
# classifiers/scams.py
import hunches as hn

taxonomy = hn.Taxonomy(
    mode="multi", labels={"scam": "Offers a fake prize ...", "satire": "Parody ..."}
)
classifier = hn.Classifier(
    "anthropic:claude-haiku-5-5", taxonomy, prompt=open("classifiers/scams.md").read()
)
```

Other notebooks then `from classifiers.scams import classifier`. Use a bundle when the evaluation should travel with it.

## Recording the evaluation

`hn.evaluate` appends every run to `.hunches/evals.jsonl` with the full prompt, so the history of what was tried is in the file. `hn.eval_log()` reads it back. If a report is written for others, state the evaluation honestly: the split, `n`, who labelled the gold rows (`final.sources` counts rows by `hunches-ui`, `imported` and unstamped), and how many times the test split was evaluated.

```python
final.sources
hn.eval_log()
final.write("reports/scams-evaluation.json")
```

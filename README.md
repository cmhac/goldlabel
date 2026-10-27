# hunches

A Python library for content analysis over a corpus that is **already embedded**: seed phrases, semantic
search, candidates, an LLM classifier checked against a hand-labelled gold set, then classified output.

You build the analysis step by step in a Jupyter notebook (or a plain script), alone or with a coding
agent, by chaining function calls whose results display themselves. The one thing that needs a screen of
its own, labelling the gold set, is a small local web page that a function call opens. There is no
application, no console script and no stored status: the notebook is the record of what you did, and the
state is plain files.

## Install

```
pip install hunches
pip install "hunches[s3]"      # boto3, for an S3 Vectors corpus
pip install "hunches[pg]"      # psycopg, for a pgvector (PostgreSQL) corpus
pip install "hunches[rds]"     # psycopg and boto3, for RDS / Aurora IAM database authentication
pip install "hunches[local]"   # Sentence Transformers, for local query embeddings (Python < 3.14)
```

Python 3.12 or newer. Tables in the examples are polars (`pip install polars`); every table also has
`.to_pandas()`, and `.rows` is always a plain list of dicts.

## The whole chain

Run it cell by cell in a notebook. [`examples/sample/walkthrough.ipynb`](examples/sample/walkthrough.ipynb)
(and the same cells as a script, `walkthrough.py`) does exactly this over a tiny corpus that ships with the
repository.

**1. Search.** Seeds are phrases a matching item could say. Each item keeps its best similarity.

```python
import hunches as hn

corpus = hn.PgCorpus(
    table="posts", text_column="body"
)  # or hn.S3Corpus(...), hn.Table("posts.parquet", ...)
seeds = hn.read_seeds("seeds.csv")  # or a plain list of strings
candidates = hn.search(corpus, seeds, embedder="openai:text-embedding-3-small")
candidates  # count, similarity bands, a warning if the backend capped the results
candidates.to_polars()
```

**2. Labels and a prompt.**

```python
taxonomy = hn.Taxonomy(
    mode="multi",  # or "single"; off_topic is built in
    labels={
        "scam": "Offers a fake prize or asks for money first.",
        "satire": "A joke.",
    },
)
clf = hn.Classifier(
    "anthropic:claude-haiku-4-5", taxonomy, prompt=open("prompt.md").read()
)
```

**3. Gold: people label.** `draw` writes pending rows with no labels. `hn.label` opens the labelling page
and returns when the person presses **Done**.

```python
gold = hn.Gold()  # .hunches/gold.jsonl
gold.draw(candidates, n=50, split="dev")
hn.label(gold, taxonomy)
```

**4. Evaluate and tune.** Evaluating the same classifier on the same rows again makes no model calls; a
changed prompt costs one call per row. Tune on the dev split.

```python
ev = hn.evaluate(clf, gold.dev, target=0.9)
ev  # metrics, per-label table, PASS/FAIL against the target, where the labels came from
ev.disagreements_to_polars()  # id, text, gold, predicted, reasoning

clf2 = clf.with_prompt(open("prompt.md").read())  # classifiers are immutable: keep both
ev2 = hn.evaluate(clf2, gold.dev, target=0.9)
```

**5. The test split, once.**

```python
gold.draw(candidates, n=50, split="test")
hn.label(gold, taxonomy)
final = hn.evaluate(clf2, gold.test, target=0.9)
```

**6. Choose a cutoff, price the run, run it.**

```python
report = hn.band_sample(
    clf2, candidates, per_band=30
)  # off-topic rate per similarity band
chosen = candidates.above(0.70)  # the cutoff is yours
est = clf2.estimate(chosen)  # calls, dollars or "?", seconds; calls no model
results = clf2.classify(chosen, out="results.jsonl", max_cost=25.0)
results.to_polars()
```

`max_cost` refuses before spending anything when the estimate is over it, and also when the model's price
is unknown. An unknown price is shown as `cost ?` with a warning, never as `$0`. `out=` makes the run
resumable: run the cell again and only the missing rows are classified.

**7. Keep the classifier.** See [Reusing a classifier](#reusing-a-classifier).

## Where files go

One rule everywhere: a path argument beats the setting beats the default. The default root is `.hunches/` in
the current directory. Change it for the process with `hn.settings.root = Path("elsewhere")` (a `pathlib.Path`) or set
`HUNCHES_DIR`.

| File | Written by | Default |
|---|---|---|
| `candidates.jsonl` (+ `.meta.json`) | `hn.search` | `.hunches/candidates.jsonl`; `out=` moves it, `out=False` keeps it in memory |
| `gold.jsonl` | `hn.Gold()` | `.hunches/gold.jsonl`; `hn.Gold("path")` |
| `evals.jsonl` | `hn.evaluate` | `.hunches/evals.jsonl`; `log=` moves it, `log=False` turns it off |
| `cache/` | model and embedding calls, and the cost ledger | `.hunches/cache`; `cache=` moves it, `cache=False` turns it off |
| `results.jsonl` | `clf.classify(out=...)` | none: a classification writes only where you tell it |

Inputs are always explicit: `hn.read_seeds("seeds.csv")`, `hn.Taxonomy.read("taxonomy.yaml")`,
`hn.Candidates.read("candidates.jsonl")`. `seeds.csv`, `taxonomy.yaml`, `prompt.md` and the notebook are
yours to commit; the library never runs git. Moving a project is moving its folder. The cache keeps
paying for itself: re-running a notebook top to bottom, or after a kernel restart, repeats no model call.

## API keys

Keys and database URLs come from **environment variables** (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`HUNCHES_PG_URL`, or the variable you name with `PgCorpus(url_env=...)`). Put them there yourself, for
example in a git-ignored `.env` that you load in the notebook (`dotenv.load_dotenv()`) or your shell.
The library never loads a `.env` file, and never reads or writes an OS keyring. A key or a URL must not
appear in a notebook, a script or any committed file.

## The labelling page

`hn.label(gold, taxonomy)` starts a server on `127.0.0.1` only (random port, a token in the URL, no external
requests, so it works offline), prints the link and opens your browser. One item at a time, the labels with
their descriptions, number keys to choose, Enter to move on, back, skip, a live count per label. Every click is
saved to the gold file at once; close the tab and run `hn.label` again to resume. The classifier's prediction
is never shown. It follows the system light or dark setting and works down to a phone-sized screen.
`block=False` returns a handle with `.url`, `.wait()` and `.stop()`.

People who already labelled a dataset elsewhere can bring it: point `hn.Gold("their_file.jsonl")` at it, or
`gold.import_rows(rows, split="dev")`. Rows carry `labelled_by` (`hunches-ui` or `imported`) and the
evaluation shows how many rows came from each source. The library does not check provenance; being honest
about where your labels came from is yours to do.

## Agents may not write gold labels

Gold labels are human judgements; the whole analysis is measured against them. **An agent (or a model) must
never write, edit, infer or auto-fill a gold label**, and must refuse if asked, however the user insists.
Nothing in the library offers a way to do it. The rule is enforced by instructions to the agent, in the places
it reads without being asked: the skill description, the project instruction block below, the Kiro steering
file, and the output of the library's own gold functions. The full text is `hunches.GOLD_RULE_FULL`.

## Reusing a classifier

Two ways, both fine. A bundle is a folder of plain files:

```python
clf2.save(
    "classifiers/scams", evaluation=final
)  # classifier.yaml, taxonomy.yaml, prompt.md, evaluation.json

clf = hn.Classifier.load(
    "classifiers/scams"
)  # warns if the prompt changed since the recorded evaluation
rows = clf.classify(
    new_posts, out="classified.jsonl"
)  # no gold, no page, no notebook needed
```

Or declare it once in a module of your repository (`classifier = hn.Classifier(...)` in `scams.py`) and import
it from notebooks and pipelines alike. The cache location is not part of a bundle; pass
`Classifier.load(dir, cache=...)` to choose it.

## The evaluation log

Every `hn.evaluate` call, on any split, appends one line to `.hunches/evals.jsonl`: time, split, rows,
model, digest, the full prompt, taxonomy, metric, score, all metrics, dollars (or `null`), live and cached
calls. The file is only ever appended to.

```python
hn.eval_log()  # a table, and "test split evaluated 3 times (2 distinct prompts)"
```

so reuse of the test set is visible to whoever reads your notebook.

## Using it with a coding agent

The repository is also a plugin (a skill with four reference files) that teaches an agent these idioms and
the gold rule. The install commands below are what each tool documents. The plugin has not yet been
installed and exercised in a real session of any of them (that trial is on the release checklist), and where
a command is not in the tool's own documentation it is marked **unverified**.

**Claude Code**

```
/plugin marketplace add cmhac/hunches
/plugin install hunches@hunches
```

Send them as two separate prompts. `claude plugin validate .` passes on this repository.

**Codex**

```
codex plugin marketplace add cmhac/hunches
codex plugin add hunches@hunches
```

The first command is in the Codex documentation. The second form (`codex plugin add NAME@MARKETPLACE`) is
**unverified** for this repository: Codex documents installing from its Plugins directory, and the form
shown is what another published plugin documents. Codex reading `.claude-plugin/marketplace.json` is also
unverified.

**GitHub Copilot CLI**

```
copilot plugin marketplace add cmhac/hunches
copilot plugin install hunches@hunches
```

or, inside a session, `/plugin marketplace add cmhac/hunches` and `/plugin install hunches@hunches`.
The marketplace command is documented; the exact `NAME@MARKETPLACE` install form is **unverified**, and so
is whether Copilot accepts this repository's marketplace entry.

**Kiro**

Copy `.kiro/steering/hunches.md` from this repository into your project's `.kiro/steering/` (it carries the
gold rule and is always included), and copy `skills/hunches/` into your skills folder. The repository also
has a root `plugin.json` (Agent Plugins 1.0) that Kiro Powers read. `npx skills add cmhac/hunches -a kiro-cli -g`
is **unverified**: it is not on Kiro's skills page.

**Any other agent**

Paste the block below into the project's instruction file (`AGENTS.md` for Codex and Copilot CLI,
`.github/copilot-instructions.md` for Copilot, `CLAUDE.md` for Claude Code) or give the agent
`skills/hunches/SKILL.md`. The same text is in `docs/agent-instructions.md`, and
`print(hunches.GOLD_RULE_FULL)` prints the rule.

### The agent instruction block

**Hard rule of the hunches library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the hunches labelling page (`hunches.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

When working with the `hunches` library (content analysis over an embedded corpus: seed phrases, semantic search, an LLM classifier checked against human-labelled gold data):

- Read `skills/hunches/SKILL.md` first, then the reference you need: `skills/hunches/references/workflow.md` (brief, seeds, taxonomy, gold, first evaluation), `skills/hunches/references/tuning.md` (reading disagreements, tuning on dev, never on test), `skills/hunches/references/running.md` (estimate, cost, `max_cost`, resuming, keys), `skills/hunches/references/reuse.md` (saved classifiers). If the skill files are not in the project, read them at https://github.com/cmhac/hunches/tree/main/skills/hunches or print the rule with `import hunches; print(hunches.GOLD_RULE_FULL)`.
- Never run a full classification without showing `clf.estimate(...)` (calls, cost, time) and getting a yes from the user.
- Never put API keys or database URLs in a notebook, script or file; they come from environment variables.

## Development

```
uv sync --all-extras
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```

No test calls a real model, AWS or database. `AGENTS.md` describes the layout and rules for contributors.

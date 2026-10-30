# Contract: the stage skills

Every skill: folder `src/goldlabel/skills/<name>/SKILL.md`, front matter `name` (= folder) and
`description` only, description <= 1024 characters ending with the canonical short gold rule, body
starting with the canonical full gold rule. Code blocks use public names only (the existing drift
test). Library call first, reason second. Each ends with the next skill's name. "Ask" means stop and
ask the user; the agent never decides it.

| Skill | Use when | Does | Ask |
|---|---|---|---|
| `goldlabel` (kept) | any goldlabel work; the entry | the hard rules, files, the stage list with the skill for each | - |
| `goldlabel-connect` | pointing at the data, a connection or format problem | build the `Table`/`PgCorpus`/`S3Corpus`, `corpus.check()` for Postgres, read the first rows, confirm id and text columns; name the extra (`goldlabel[pg]`) on an import error; reshape with a short polars script that writes a new file and leaves the source alone; never drop or repair rows silently | where the data is; the environment variable names; which column is text |
| `goldlabel-search-terms` | choosing how to find candidates | no embeddings -> keywords or regex (`regex=True`, `(?i)`, `server_side` for big Postgres tables); embeddings -> seeds and the embedder the corpus used; or the whole corpus; write `seeds.csv`; present all as a proposal | the brief; which seeds/terms are right; whether to use the whole corpus |
| `goldlabel-taxonomy` | the labels are not decided | loop: read random samples, run keyword/seed searches, read near-misses, write up the kinds of items found with quoted ids, propose labels with 1-2 sentence descriptions and boundary notes; optional back and forth (more examples for a boundary, merge/split, one change at a time); save `taxonomy.yaml` only after approval; notes only, nothing written to a gold path | `single` or `multi`; each label description; stop for approval |
| `goldlabel-candidates` | running and judging candidate generation | `get_candidates`, `bands()`, `top_seeds`, `sample`; which terms bring in what; reword a seed or term rather than touch the classifier; keyword/whole-corpus lists have no bands | the similarity cutoff; whether the list is good enough |
| `goldlabel-tune` | gold set, evaluations, prompt, test split | gold advice (sizes, `counts`, `orphaned`, which rows to `draw`); open `gl.label` for people (never labels, refuses and offers help if asked); import a human-labelled file unchanged and report who labelled it; evaluate dev, read `disagreements`, one change at a time, compare flipped rows, stop rules; quoted prompt examples must not be gold rows; final test evaluation once; if low and the user wants to continue: explain the rows are spent, ask for a yes, `gold.fold_test()`, `gold.draw(candidates, n, split="test")`, people label, no test evaluation until all labelled | target score; each prompt/description change; whether to fold (explicit yes); whether to spend on a large dev run |
| `goldlabel-run` | the prompt is final; estimate, cost, full run | `clf.estimate(...)` shown first (`cost ?` with a warning if unknown), explicit yes, `clf.classify(..., max_cost=...)`, `clf.save`, where the output is, reuse in a pipeline | whether to spend; the `max_cost` |

The existing references (`workflow.md`, `tuning.md`, `running.md`, `reuse.md`) stay under
`goldlabel/references/` and the stage skills link to them by path rather than copy them; where a
stage skill and a reference say the same thing, the reference is trimmed so the rule lives once.
`tuning.md` gains the fold step and loses "suggest a fresh test split" as the only option.

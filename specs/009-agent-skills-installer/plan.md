# Implementation Plan: Workflow agent skills and a one-command installer

**Branch**: `claude/agent-skills-harness-spec-ht497z` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-agent-skills-installer/spec.md`

## Summary

Move the skill into the package (`src/goldlabel/skills/`) so the wheel ships it, split it into one
skill per stage plus the existing overview, add a `goldlabel install` command that copies those
folders to the places the four agents read (standard library only, no new dependency), add
`Gold.fold_test()` for the spent test split, and amend the constitution (Principle VI and the stack;
Principle I untouched, as the user confirmed). Facts are in [research.md](research.md), the command
and skill rules in [contracts/](contracts/), the new data in [data-model.md](data-model.md), and the
end-to-end check in [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python 3.12+ (`pyproject.toml`).

**Primary Dependencies**: none added. `argparse`, `importlib.resources`, `shutil`, `pathlib`, `os`.

**Storage**: files. Skill folders and one steering file written by the installer; one appended line
type in `evals.jsonl` and one `split` rewrite in `gold.jsonl` by the fold.

**Testing**: `pytest` with `tmp_path`; the installer is tested with a fake home (`monkeypatch` of
`Path.home` / `HOME`), no network. Fold tested in the end-to-end fixture with the simulated human
labelling over HTTP. Skills tested by the existing drift tests, extended.

**Target Platform**: Linux, macOS and Windows shells that run Python 3.12 (paths via `pathlib`;
symlinks are not used).

**Project Type**: library with a small console command, shipped also as an agent plugin.

**Performance Goals**: none.

**Constraints**: importing `goldlabel` still does no I/O and does not import `goldlabel.cli`; the
command writes only the files it reports; the wheel must contain the skills and the console script.

**Scale/Scope**: 7 skill folders (about 40 KB of Markdown), one new module (about 120 lines), one
new method (about 30 lines), documents and tests.

## Constitution Check

*Gate: must pass before research; re-checked after design.* The `ponytail` skill was invoked before
the spec and again before this plan and its ladder applied (does it need to exist, already in the
code base, standard library, installed dependency, minimum code). The user waived
`/ponytail-review` for this feature on 2026-10-30, so it is not run before `/speckit-implement`
(Principle III normally requires it; recorded here and in the final report).

| Principle | Check | Result |
|---|---|---|
| I. Gold rule | Unchanged and not reworded. Every skill carries the canonical text, drift-tested. The fold changes a row's `split` and nothing else, on the precedent of `draw` and `remove` rewriting the file; a test pins every other field byte-identical. The installer cannot read or write gold (FR-022, a test greps its imports). The user confirmed this reading on 2026-10-30. | Pass |
| II. Ponytail | `argparse` and `shutil` instead of a library (no library covers four agents, research R2). One module. No registry: the agent table is a dict literal. | Pass |
| III. Spec Kit | Spec, plan, tasks under `specs/009-...`; generated Spec Kit files untouched. `/ponytail-review` waived by the user (above). | Pass, waiver recorded |
| IV. Test-first | Red tests first for each task; expected paths and bytes written by hand in the tests; no network, no real agent. | Pass |
| V. No hidden state | The installer reads no config and keeps no record of what it installed (no manifest file); idempotence is a byte comparison with the shipped files. | Pass |
| VI. Honest costs, logged evaluations | The test split may now be folded and re-drawn on the user's explicit yes; the fold is logged, never silent. Amendment needed (MINOR), done through `/speckit-constitution` with the user's approval, which the user has given for this change. | Pass, amendment task |
| VII. Notebook library | No change to result objects; `eval_log` repr states the fold in words. `import goldlabel` imports neither `cli` nor `argparse`-heavy code. | Pass |
| Packaging | Skills are the product's agent surface and stay drift-tested; dev skills (`.agents/skills`, `.claude/skills`) are not shipped. The constitution's "Agent packaging" line is updated for the new location. | Pass, amendment task |
| Podman | No container commands. | Pass |

Re-check after design: no violation. Two amendments are tasks, not exceptions.

## Project Structure

### Documentation (this feature)

```text
specs/009-agent-skills-installer/
├── spec.md
├── plan.md              # this file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md           # the command, flags, output, exit codes
│   └── skills.md        # the stage skills: names, descriptions, what each asks the user
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source code

```text
src/goldlabel/
├── cli.py                    # new: `goldlabel install`, argparse, stdlib only
├── gold.py                   # + Gold.fold_test()
├── evaluation.py             # EvalLog reads fold records; _test_line says so
└── skills/                   # moved from skills/goldlabel/ and split (one folder per stage)
    ├── goldlabel/            # overview + the four references, unchanged in substance
    ├── goldlabel-connect/SKILL.md
    ├── goldlabel-search-terms/SKILL.md
    ├── goldlabel-taxonomy/SKILL.md
    ├── goldlabel-candidates/SKILL.md
    ├── goldlabel-tune/SKILL.md
    └── goldlabel-run/SKILL.md
pyproject.toml                # + [project.scripts] goldlabel = "goldlabel.cli:main"
.claude-plugin/plugin.json    # + "skills": ["./src/goldlabel/skills"]
.kiro/steering/goldlabel.md   # unchanged text; a test pins it to cli.steering_text()
tests/                        # test_cli.py (new); test_skills.py, test_docs.py, test_gold.py,
                              # test_evaluation.py, test_e2e.py extended; test_public_api.py checks
                              # `import goldlabel` does not import goldlabel.cli
```

**Structure Decision**: one source of skills inside the package, because the wheel ships only the
package and a second root copy would need a sync test. The root `skills/` folder is removed; Claude
Code's plugin loader is pointed at the package folder by the plugin manifest's `skills` path (R3).
The overview skill keeps the name `goldlabel`, so plugin users still get `/goldlabel:goldlabel`.
Stage skills are folded to six (not seven): stages 1 and 2 stay apart because the corpus
connection is run once and search terms are revisited many times; the gold advice, the tuning loop
and the test-split handling are one skill (`goldlabel-tune`) because they share the dev/test rule.

## Design

**Installer** (`cli.py`). `goldlabel install [AGENT ...] [--global] [--dir PATH] [--force]
[--dry-run]`. `AGENT` is `claude`, `codex`, `copilot`, `kiro` or `all`; with none given and a
terminal, the command lists the choices and exits 2 (no prompts). A dict maps each agent to its
project and user skills folders (R1); `codex` and `copilot` share `.agents/skills`, so the set of
target folders is deduplicated before writing. For each target folder and each shipped skill it
compares file bytes: identical -> "up to date"; absent -> write via a temporary sibling folder and
`os.replace`; different -> refuse unless `--force`. Kiro also gets `steering/goldlabel.md` next to
its skills folder, text from `steering_text()` (front matter plus `GOLD_RULE_FULL` plus the
pointer lines). `--dir PATH` writes the skill folders to `PATH` and prints that the agent must be
pointed at it. It prints every path, status and a next step per agent (reload command for Copilot,
restart note, the Kiro custom-agent `resources` line to add). Skills are read through
`importlib.resources.files("goldlabel") / "skills"`, so a wheel, a source tree and an editable
install behave the same. Exit codes: 0 done or nothing to do, 1 refused (differs, unwritable, bad
agent name), 2 usage.

**Fold** (`gold.py`). `Gold.fold_test(log=None)`: read the rows and the evaluation log; refuse
(`GoldError`) when a test row is pending, when there is no labelled test row, or when the log has no
test-split evaluation since the last fold; rewrite the labelled test rows with `split="dev"` and
every other field untouched; append `{"event": "test_folded", "time", "rows": n}` to `evals.jsonl`.
`eval_log()` puts event lines in `EvalLog.folds` and keeps `rows` evaluations only, so `to_polars`
is unchanged; the "test split evaluated k times" line counts only evaluations after the last fold
and adds "k rows folded into dev on <date>". A fresh split is `gold.draw(candidates, n, split="test")`
as today (folded ids are in the file, so they are excluded).

**Skills.** Each `SKILL.md`: front matter `name` (= folder), `description` (when to use, then
`GOLD_RULE_SHORT`, at most 1024 characters), body starting with `GOLD_RULE_FULL`, then the steps with
library calls first, the decisions it must ask the user, and the stop conditions. Shared text (the
gold rule, "ask the user" list, the order of stages) is not repeated by hand beyond the rule: each
stage skill ends with a one-line "next skill". Shipped front matter uses only `name` and
`description` (the intersection all four accept, R1). The taxonomy skill's loop and the tuning skill's
fold step are specified in [contracts/skills.md](contracts/skills.md).

## Complexity Tracking

No violations to justify. Rejected additions: a third-party installer library (R2), a manifest of
installed files (no hidden state), a root `skills/` copy plus a sync test (R3).

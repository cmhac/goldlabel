# Feature Specification: Ordered stage skills and minimal agent code

**Feature Branch**: `claude/sharp-galileo-vi4k0k` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Make the goldlabel agent skills a strict, regimented, Spec Kit-style sequence, and keep agent-written code minimal."

## Where things are today (assessment, 2026-11-04)

Two sources: the skills in this repository, and three notebooks the user supplied as examples of output they did not like (`2026-11-02-somalis`, `2026-11-03-trump-on-the-ballot`, `2026-11-03-existential-election-emails`; cell ids below are from those files).

**The skills do not enforce an order.**
- `goldlabel/SKILL.md` says "a guide to idioms, not a procedure: do what the user asks for, in the order that fits"; `references/workflow.md` says "Skip, repeat or reorder".
- Stage skills have a prose "Goal" and a `## Next` on only three of six (connect, search-terms, candidates). None has an entry check, a numbered procedure (except two inner loops) or an exit check. Spec Kit's skills end with a "Done When" list and a completion report naming the next command.
- `tests/test_skills.py` checks names and the gold rule, not order.
- The Somali notebook shows the cost. Gold rows were drawn from two different candidate lists (the whole corpus at `df889478`, then a regex list at `34f13a79`, after the first evaluation), the full classification ran on the whole-corpus list (`ba3d9405`), and the test fold came after the full run (`95a5ba63`). Candidates were changed after tuning began and the run happened before the test split was settled.

**Agents write code that is not goldlabel, and most of it is a guard or a cache.** What the notebooks contain:
- *A cache of the input data* (all three): fetch the data, `if not RAW.exists(): ... write_parquet(RAW)`, then read it back (`36198549`, `66e7afaa`, `6d8fee58`), with a comment "Snapshot, so every rerun reads the same segments". `gl.Table` already takes a DataFrame, so the parquet round trip and the exists-check are not needed to use the library.
- *Guards that stand in for a cache of gold and evaluation results*: `if not gold.all.rows: gold.draw(...)` (`4ba5c4fb`, `df889478`, `d093f22d`), a second draw guard that reloads `gl.Gold()` (`aee728ab`), and "evaluate the test split at most once" built from `gl.eval_log()` (`3307d71c`) that prints the recorded row instead of calling `evaluate`.
- *Hand-written helpers and long constants*: a fetch function with SSM and psycopg (`36198549`); about 60 lines of regex constants plus `near()` and `after()` helpers (`d41bea31`); about 100 lines of shingle/Jaccard deduplication written twice, once more for the three-month run (`297a582b`, `76e7fe02`, `4605d4b0`, `c4cac451`).
- *Prompt edited in the notebook by string replacement* (`e8e475d0`), although the skills say to keep the prompt in `prompt.md`.
- *Housekeeping and decoration*: `os.chdir` to find `pyproject.toml`, `load_dotenv` from another repository's `.env` (the library itself never loads a `.env`), repeated imports, `assert MAX_COST is not None`, a chart cell pasted twice.
- *Analysis after the classifier*: weekly aggregates, Altair charts, an f-string "fact-check" section with asserts, CSV export (Somali notebook, `acec2f33` onward). Whether the user asked for these is not visible in the notebook; they are outside what goldlabel does.

**What the skills say about it.** Nothing forbids any of the above. `goldlabel-connect` teaches a polars transform that writes a file; `goldlabel-taxonomy` suggests a notes file; `goldlabel-tune` shows `open("prompt.md").read()` and an `assert`. No skill says "write only goldlabel calls".

**Not a library gap, as far as these notebooks show.** The library already caches model calls, so re-running `evaluate` or `classify` costs nothing, and it writes seed candidates. An earlier draft of this spec proposed new library calls (`Evaluation.read`, saving keyword lists by default). The notebooks give no evidence they are needed, so they are out. The one real tension is in the open question below.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The agent runs the stages in one fixed order and always says what is next (Priority: P1)

A user asks an agent to analyse a corpus with goldlabel. The agent starts at `goldlabel-connect` and works through search-terms, taxonomy, candidates, tune and run, one stage at a time. At the end of each stage it tells the user, in a fixed form, that the stage is done, what was produced, and the exact next skill to run. If the user asks to jump ahead (for example to classify before there is a taxonomy), the agent says which earlier stage is not finished and offers to do it first; it jumps only on the user's explicit say-so.

**Why this priority**: this is the user's main complaint. It is also how people learn the workflow, and how they notice they are off it.

**Independent Test**: for each stage skill, read it and check by hand that it has an entry check, numbered steps, an exit check and a closing "next" line naming the following skill; then follow the chain connect -> run over the sample corpus and check no step is missing.

**Acceptance Scenarios**:

1. **Given** a user who has not started, **When** the agent loads the overview skill, **Then** it states the stages as an ordered procedure (connect, search-terms, taxonomy, candidates, tune, run), says to start at the first, and says which stages are optional.
2. **Given** a stage skill is finished, **When** the agent reports to the user, **Then** the report names what was produced, what the user approved, and the exact next skill, in the same form for every stage.
3. **Given** a user asks for a later stage while an earlier one has no result (no corpus connected, no approved taxonomy, no passing dev score, no test evaluation), **When** the agent loads that stage skill, **Then** its entry check fails, the agent names the missing stage and offers to run it, and does not proceed unless the user says to skip.
4. **Given** the user wants to repeat a stage (reword a seed, change a label, tune again), **When** they say so, **Then** the skills say which later stages must be re-run and the agent tells the user.
5. **Given** the last stage (`goldlabel-run`), **When** it finishes, **Then** the report says the sequence is complete and names the optional follow-ups (save and reuse the classifier, report).

---

### User Story 2 - The agent writes only goldlabel calls (Priority: P1)

A user watches an agent build the analysis in a notebook or script. The cells contain goldlabel calls and nothing else the library does not need. The agent does not write a snapshot or cache of the input data, a guard that skips a library call because it was already run, helper functions, long constants, string-replacement of the prompt, environment loading, or analysis after the classifier. When something seems to need non-goldlabel code, the agent stops, shows what it would write and why, and writes it only when the user says yes.

**Why this priority**: the user's second complaint. Every extra line is something a reader has to trust, and in all three notebooks the largest blocks were not goldlabel.

**Independent Test**: take each stage skill's code blocks and the sample walkthrough and count the lines that are not goldlabel calls or the short list of allowed constructs (FR-007); the count is zero. Then give an agent the Somali, Trump and email briefs on the sample corpus and list any line in its notebook that is not a goldlabel call and was not approved.

**Acceptance Scenarios**:

1. **Given** any stage skill, **When** an agent follows it, **Then** every code block is goldlabel calls plus the allowed constructs, and the skill states "write only goldlabel calls; anything else needs the user's yes, shown first".
2. **Given** the data must be fetched from a database or service the library cannot read directly, **When** the agent writes the query, **Then** it is the single approved non-goldlabel step, its result goes straight into `gl.Table(df, ...)`, and no snapshot file or exists-check is written unless the user asks for one.
3. **Given** a notebook is re-run, **When** the agent would add a guard around `draw`, `evaluate` or a fetch, **Then** the skills tell it not to, and what to say to the user instead (see the open question).
4. **Given** the prompt, **When** it is more than a line, **Then** it lives in `prompt.md` and a change is an edit to that file followed by `with_prompt`, never a `.replace` chain in the notebook.
5. **Given** the classified output exists, **When** `goldlabel-run` finishes, **Then** the agent stops and names the optional follow-ups; charts, deduplication, aggregates, fact-check cells and exports are written only if the user asks for them.
6. **Given** a task the skills do not cover, **When** the agent would write a helper, **Then** it asks instead.

---

### User Story 3 - A drift test keeps the order and the rule from rotting (Priority: P2)

When anyone edits a stage skill, a test fails if the stage loses its entry check, numbered procedure, exit check, closing next step, or its link to the next skill, or if a skill shows a code line that is not a goldlabel call outside a marked section.

**Why this priority**: the skills drifted into menus once; the same will happen again without a test. This is the same job `tests/test_skills.py` does for names and the gold rule.

**Independent Test**: delete the closing "next" line from one stage skill and check the test fails and says which.

**Acceptance Scenarios**:

1. **Given** the six stage skills, **When** the test runs, **Then** they form an unbroken chain from the first to the last, and each names the same next skill in its closing line as the chain says.
2. **Given** a stage skill without an entry check, a numbered procedure or an exit check, **When** the test runs, **Then** it fails and names the skill and the missing part.
3. **Given** a code block in a skill that calls something other than the library or a documented read, outside a section marked as user-directed, **When** the test runs, **Then** it fails.

---

### Edge Cases

- A user who has already done earlier stages in an earlier session (a taxonomy file, a gold file exist): the entry check passes by finding the artefacts, and the agent tells the user which stages it is treating as done and why, and asks to confirm.
- A user who brings a human-labelled gold file: `goldlabel-tune` still applies; the gold rule is untouched.
- A user who wants to work on one stage only (for example just tune a prompt): allowed; the entry check names what it assumed and the agent says what it did not check.
- The test-split recovery path in `goldlabel-tune` (fold, redraw, tune, evaluate once): stays inside `goldlabel-tune` as numbered steps; it does not become a seventh stage.
- Agents with no skill tool (the instruction block in `docs/agent-instructions.md`): the block names the order too.
- Where an agent honestly cannot tell whether code is "goldlabel code" (for example `pl.col` inside `where=`): the skill lists the few non-library constructs it expects (a polars expression for `where=`, a seeds file path, the reads the library names) and treats those as allowed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The overview skill MUST state the stages as an ordered procedure (connect, search-terms, taxonomy, candidates, tune, run), MUST tell the agent to begin at the first, and MUST NOT say the skills are a guide to idioms or that stages may be reordered at will.
- **FR-002**: Each of the six stage skills MUST have, in this order and with the same headings: an entry check (what must already exist or have been approved), a numbered procedure, an exit check (what must be shown to the user and what they must have approved), and a closing "next" line naming the exact next skill. The last stage's closing line MUST say the sequence is complete.
- **FR-003**: When an entry check fails, the skill MUST tell the agent to name the missing earlier stage, offer to run it, and proceed only on the user's explicit instruction to skip.
- **FR-004**: Each stage skill MUST say, for a repeat of that stage, which later stages must be re-run.
- **FR-005**: Optional steps MUST be marked as optional in the stage where they belong (for example the corpus `where=` filter, the band sample, saving and reusing a classifier, folding the test split) and MUST say which stage they sit inside; none becomes a stage of its own.
- **FR-006**: The overview and every stage skill MUST state the minimal-code rule: write only goldlabel calls (plus the few documented non-library constructs); any other code, including caches of input data or evaluation results, helpers and reshaping, only when the user directs it, shown first.
- **FR-007**: Every code block in the skills MUST consist of goldlabel calls and a short list of allowed constructs (a polars expression for `where=`, a path to a seeds or prompt file and its read, the corpus-fetch step of FR-008), except in sections marked as user-directed; the skills MUST NOT teach writing a snapshot or cache, a guard around a library call, a helper function, a class or a transform that is not user-directed.
- **FR-008**: When the data cannot be read by a goldlabel corpus, the skills MUST allow one fetch step, written only after the user agrees, whose result is passed directly to `gl.Table`; they MUST NOT have it write and re-read a snapshot file unless the user asks.
- **FR-009**: The skills MUST say how to handle a notebook being re-run without writing guards [NEEDS CLARIFICATION: see the open question].
- **FR-010**: The skills MUST keep a prompt longer than a line in `prompt.md` and change it by editing that file.
- **FR-010a**: The skills MUST say that nothing is done after `goldlabel-run` except what the user asks (charts, deduplication, aggregates, exports, fact-check cells), and that `.env` files are not loaded by the agent: keys are expected in the environment.
- **FR-011**: The gold rule text in every skill MUST stay verbatim as today; this change MUST NOT alter `gold_rule.md` or any way a gold label is set.
- **FR-012**: A test MUST fail when a stage skill lacks any part named in FR-002, when the chain of closing lines is broken, or when a code block breaks FR-007.
- **FR-013**: `docs/agent-instructions.md`, the README block that equals it, the Kiro steering file and the README MUST state the order and the minimal-code rule in the same words as the overview, and the existing drift tests MUST pass with them.
- **FR-014**: The walkthrough (`examples/sample/walkthrough.ipynb` and `.py`) MUST stay equal to each other, MUST contain only goldlabel calls (the hand-made embedder stand-in is a documented exception), and MUST follow the stage order.

### Key Entities

- **Stage skill**: one of the six, with the four parts of FR-002.
- **Entry check / exit check**: a short list of conditions a person can verify; the entry check is read against files and approvals that exist, never against a stored status (the library keeps none).
- **Closing line**: the fixed-form last line of a stage, naming the next skill.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 6 of 6 stage skills have the four parts of FR-002 and an unbroken chain from first to last; the test for it passes, and fails when any part is removed.
- **SC-002**: 0 code lines in the skills, outside user-directed sections, that are not goldlabel calls or the listed non-library constructs.
- **SC-003**: Following the skills over the sample corpus, a reviewer finds the notebook the agent wrote contains 0 lines of non-goldlabel code that the user did not ask for.
- **SC-004**: In a trial of the same request given to a fresh agent in each of Claude Code and one other agent, 2 of 2 start at the first stage, announce the next stage at the end of each stage they complete, and refuse (offer the earlier stage) when asked to skip ahead.
- **SC-005**: Re-running the sample walkthrough from the top a second time makes 0 model calls and writes no file that is not the library's own, with no guard code in the notebook (subject to the open question).
- **SC-006**: Ruff, ty and pytest pass; the gold rule drift tests pass unchanged.

## Deliberately skipped

- A command, state file or stored status that records which stage the user is on (the code and files are the record; the entry check reads files).
- A new top-level stage, or a runner that executes the stages (Spec Kit's `workflow.yml` equivalent).
- New skills for the optional steps; they stay inside the stage they belong to.
- A linter that parses notebooks an agent produced; the check is the skills' own text and the trial.
- New library calls to reload candidates or evaluations (the notebooks show no need).
- Making `gold.draw` or `evaluate` safe to re-run, unless the user chooses that in the open question.
- Changing the gold rule, the labelling page, `fold_test`, metrics or any search backend.
- Splitting or renaming the six skills, or changing `goldlabel install`.
- Hooks that stop an agent writing non-goldlabel code; the rule is text plus a trial.

## Assumptions

- "Spec Kit-style" means the pattern of ordered skills that each end by naming the next command and that carry a completion checklist, not Spec Kit's files or CLI.
- Strict means refuse-and-offer by default, with the user able to override in words; it is not a hard block.
- The minimal-code rule is carried in skill text and a trial, because skills cannot be enforced by the library.
- The list of non-library constructs allowed is short: a `where=` polars expression, a path to a seeds file, the text of a prompt read from a file, and the documented reads.
- The three supplied notebooks are representative; which lines the user disliked is inferred from the user's description (caches of input data and of gold evaluation results, and verbose code), not told cell by cell.

## Open question for the user

Agents add guards because a re-run cell has side effects: `gold.draw(...)` adds another 50 pending rows, and a second `evaluate` on the test split adds a second test entry to the evaluation log. What should the skills tell an agent to do?

- **A. Tell the agent to write no guard**, and to tell the user which cells are run-once (draw, test evaluation). Smallest; the user owns the re-run risk.
- **B. Change the library so a second `draw` of the same split and a second test `evaluate` are safe.** The notebooks stay clean; it is a library change with its own spec, and it touches the "test split is evaluated once" rule.
- **C. Tell the agent to put run-once cells in a separate marked cell with a comment**, no code guard.

My recommendation is A, then B only if A proves irritating.

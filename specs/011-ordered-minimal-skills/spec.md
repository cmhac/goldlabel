# Feature Specification: Ordered stage skills and minimal agent code

**Feature Branch**: `claude/sharp-galileo-vi4k0k` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Make the goldlabel agent skills a strict, regimented, Spec Kit-style sequence, and keep agent-written code minimal."

## Where things are today (assessment, 2026-11-04)

Read from the repository, not from agent transcripts (see the open question):

- **No enforced order.** `goldlabel/SKILL.md` says "This is a guide to idioms, not a procedure: do what the user asks for, in the order that fits", and `references/workflow.md` says "Skip, repeat or reorder as the user's work needs". The six stage skills do end with a `## Next` pointer (connect, search-terms, candidates) or name their neighbours in the opening line (taxonomy, tune, run), but the wording varies, `goldlabel-run` and `goldlabel-tune` have no `## Next`, and nothing makes an agent check that the previous stage is finished before starting the next.
- **No entry or exit checks.** A stage skill states a "Goal" and what comes "Before this", as prose. Nothing says what must exist (a file, an approved list, a number the user chose) before the stage starts, or what must be shown to the user before it is done. Spec Kit's skills close with a "Done When" checklist and a completion report that names the next command; goldlabel's do not.
- **Steps are menus, not procedures.** The skills show alternatives side by side (three corpus kinds, keywords or seeds or whole corpus, unattended or together) and the numbered steps appear in only two places (the taxonomy loop and the test-split recovery).
- **Skills invite non-library code.** `goldlabel-connect` teaches a hand-written polars transform that writes a new file; `goldlabel-taxonomy` suggests a `taxonomy-notes.md` file and list-comprehension filters; `goldlabel-tune` shows `open("prompt.md").read()` and an `assert` snippet; `goldlabel-search-terms` writes `seeds.csv` with polars. No skill says "write nothing that is not a goldlabel call unless the user asks".
- **Possible library gaps that push agents to write caches.** The library already caches model calls (`evaluate`, `classify`) and writes `.goldlabel/candidates.jsonl` for seed searches. But keyword and whole-corpus candidates are written only when `out=` is passed, so re-running a notebook re-reads the corpus; `Candidates.read` exists but no skill teaches it (only the README mentions it); and `Evaluation` has `write` but no `read` (the same results can only be recovered by re-running `evaluate`, or from `gl.eval_log()`, which keeps metrics, not the disagreements).
- **Drift tests cover names, not order.** `tests/test_skills.py` checks that code blocks use real names and the gold rule is verbatim. Nothing checks that every stage skill has an entry check, a numbered procedure, an exit check and a next step, or that the chain connect -> run is unbroken.

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

A user watches an agent build the analysis in a notebook or script. The cells contain goldlabel calls (and the plain file reads the library asks for, such as the path of a seeds file) and nothing else. The agent does not write caching of input data, caching or saving of evaluation results, helper functions, wrapper classes or data-reshaping code. When something seems to need non-goldlabel code, the agent stops, says what it would write and why, and asks; it writes it only when the user says yes.

**Why this priority**: the user's second complaint. Every extra line is something a reader has to trust, and the library already caches.

**Independent Test**: take each stage skill's examples and count the lines that are not a goldlabel call or a documented library read; the count is zero outside the sections the user directs. Then run a reviewer (human or agent) over the notebook an agent produced for the sample corpus and list any line that is not a goldlabel call.

**Acceptance Scenarios**:

1. **Given** any stage skill, **When** an agent follows it, **Then** every code block it shows is made of goldlabel calls only, and the overview and each stage state the rule "write only goldlabel calls; anything else needs the user's yes".
2. **Given** a notebook is re-run, **When** the agent wants to avoid repeating work (a corpus read, an evaluation), **Then** the skill tells it to use the library's own persistence (the file the library writes, and its `read`), not to write its own cache.
3. **Given** data that the library cannot read, **When** the agent proposes a transform, **Then** it shows it, says why the library cannot do it, and runs it only on the user's yes (this exists today in `goldlabel-connect`; it stays, but behind the rule).
4. **Given** a task the skills do not cover, **When** the agent would otherwise write a helper, **Then** it asks the user instead.

---

### User Story 3 - The library covers what agents were hand-rolling (Priority: P2)

A user re-opens a notebook the next day. The candidates they made, and the evaluation they scored, come back with one library call each, with no code of the agent's own. Anything an agent had to write to get that is closed in the library.

**Why this priority**: telling agents not to write caches only works if the library does not leave them a reason. P2 because the skill text (stories 1 and 2) delivers most of the value alone.

**Independent Test**: in a temporary directory, run a candidate search of each kind (seeds, keywords, whole corpus) and an evaluation, start a fresh process, and bring each result back with one library call; check the result equals the original.

**Acceptance Scenarios**:

1. **Given** keywords or a whole-corpus candidate list was made, **When** the user re-runs the notebook, **Then** it can be re-loaded with one library call without re-reading the corpus [NEEDS CLARIFICATION: should keyword and whole-corpus lists be written to `.goldlabel/candidates.jsonl` by default like seed lists, or stay opt-in with `out=` and only be taught better?].
2. **Given** an evaluation was run, **When** the user starts a fresh session, **Then** the evaluation (metrics, disagreements) is available again with one library call and no model call.
3. **Given** the skills teach a reload call, **When** the drift test runs, **Then** every call shown exists with that name.

---

### User Story 4 - A drift test keeps the order and the rule from rotting (Priority: P2)

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
- **FR-007**: Every code block in the skills MUST consist of goldlabel calls and the documented non-library constructs, except in sections marked as user-directed; the skills MUST NOT teach writing a cache, a helper function or a class.
- **FR-008**: The skills MUST teach the library's own persistence for re-loading work (`Candidates.read`, the evaluation reload from FR-009, `Taxonomy.read`, `Classifier.load`) wherever an agent might otherwise write its own.
- **FR-009**: The library MUST let an evaluation written by the library be read back with one call and no model call.
- **FR-010**: The library MUST let a keyword or whole-corpus candidate list be reloaded with one call without re-reading the corpus (the mechanism is decided in the clarification under Story 3).
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
- **SC-005**: An evaluation and a candidate list of every kind are brought back in a fresh process with one library call each, equal to the originals, with 0 model calls.
- **SC-006**: Ruff, ty and pytest pass; the gold rule drift tests pass unchanged.

## Deliberately skipped

- A command, state file or stored status that records which stage the user is on (the code and files are the record; the entry check reads files).
- A new top-level stage, or a runner that executes the stages (Spec Kit's `workflow.yml` equivalent).
- New skills for the optional steps; they stay inside the stage they belong to.
- A linter that parses notebooks an agent produced; the check is the skills' own text and the trial.
- Changing the gold rule, the labelling page, `fold_test`, metrics or any search backend.
- Splitting or renaming the six skills, or changing `goldlabel install`.
- Hooks that stop an agent writing non-goldlabel code; the rule is text plus a trial.

## Assumptions

- "Spec Kit-style" means the pattern of ordered skills that each end by naming the next command and that carry a completion checklist, not Spec Kit's files or CLI.
- Strict means refuse-and-offer by default, with the user able to override in words; it is not a hard block.
- The minimal-code rule is carried in skill text and a trial, because skills cannot be enforced by the library.
- The list of non-library constructs allowed is short: a `where=` polars expression, a path to a seeds file, the text of a prompt read from a file, and the documented reads.
- The assessment above comes from the repository only. I have not seen the agents' notebooks.

## Open question for the user

- Which non-goldlabel code have you actually seen agents write (caches of the corpus, of candidates, of evaluation results, something else)? Pasting one or two notebooks would let us close the exact gap instead of the ones I inferred.

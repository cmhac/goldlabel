# Feature Specification: `/goldlabel` as a complete entry point

**Feature Branch**: `claude/tender-heisenberg-vfoip3` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "Skills: make /goldlabel a complete entry point and teach the new labelling page" (GitHub issue [#27](https://github.com/cmhac/goldlabel/issues/27))

## Where things are today (assessment, 2026-11-09)

A tester could not tell which skill to call first. `/goldlabel` started him at stage 1 although he had already done several steps, and the skill invited label changes that it had no way to support.

- `src/goldlabel/skills/goldlabel/SKILL.md` says "Start at the first" stage. It has no step that looks at what the user already has, so a user with a connected corpus, a taxonomy and candidates is walked through `goldlabel-connect` again.
- The overview lists the six stages and the rules, but says nothing about *how to talk to the user* at a stage (what to ask, what to show, when to stop and wait). That lives only inside each stage skill, so an agent that loads just the overview is not equipped to guide the whole sequence, and a user who names a stage skill directly never sees the overview at all.
- The labelling page (013, 015: `goldlabel label`, `gl.label`) is mentioned in one line of `goldlabel-tune` and one bullet of the instruction block. The overview does not say what the page can do (browse datasets, samples and rows, open a row by id, label what is pending, revise a row, read each evaluation's disagreements with a STALE flag), how to start it, or that every label revision goes through it. `goldlabel-tune`'s disagreement reading (step 4 and 5) works from `ev.disagreements_to_polars()` only.
- `.kiro/steering/goldlabel.md` and `docs/agent-instructions.md` already carry the 015 bullet about `goldlabel label`; the `POINTERS` text in `src/goldlabel/cli.py` writes the same bullets. The three are one text in three places.
- `tests/test_skill_stages.py` checks the order, the four parts of each stage, the code rule and the instruction block, and nothing about a progress check, the page, or where to start.
- The issue's text says `gold.jsonl`. Since 015 a gold dataset is `gold.json` (or `gold-<name>.json`); this spec uses the current name.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The agent resumes at the next unfinished stage (Priority: P1)

A user opens an agent and calls `/goldlabel` in a project that already holds work: a notebook with a connected corpus, a taxonomy and a candidates call, maybe a `.goldlabel/` folder with a gold file and evaluations. The agent first reads the notebook or script and the storage folder, works out which of the six stages have evidence of being done, tells the user what it found, and offers to resume at the first stage without evidence instead of at stage 1. The user confirms or corrects, and the agent loads that stage's skill.

**Why this priority**: this is the tester's failure and the issue's first two checklist items. Nothing else in the issue matters if the first call goes to the wrong stage.

**Independent Test**: hand-written fixtures (a notebook with stages 1 to 3 done, one with all six, an empty directory) are described to a reader of the skill, who must name the same resume stage a maintainer would; the drift test checks the progress-check text is there and names every stage's evidence.

**Acceptance Scenarios**:

1. **Given** no notebook, script or storage folder, **When** the agent loads the overview, **Then** it says nothing is done yet and starts at `goldlabel-connect`.
2. **Given** a notebook that builds a corpus, a taxonomy and calls `get_candidates`, and no classifier, **When** the agent runs the progress check, **Then** it reports stages 1 to 4 as done by name, with the evidence it saw (the call or file), and offers `goldlabel-tune` as the next stage.
3. **Given** the agent's reading is a guess (a variable that looks like seeds but nothing uses it, a gold file from another notebook), **When** it reports, **Then** it says which stages it is unsure of and asks the user rather than assuming; evidence is never enough to skip a stage on its own, the user's yes is.
4. **Given** the user says "start over" or names a stage, **When** the agent has reported the progress, **Then** it follows the user and applies that stage's entry check as usual.
5. **Given** the check found stage 6 done (a full `classify` ran), **When** it reports, **Then** it says the sequence is complete and offers what is optional (reuse, a second corpus, review in the page), not stage 1.

---

### User Story 2 - The overview alone is enough to guide a user through every stage (Priority: P1)

An agent that loads only `/goldlabel` knows the whole conversation: for each stage what it is for, what to ask the user, what to show them, what they must approve before the next stage, and what to tell them at the end. A user who is new to goldlabel can be led from "I have some data" to a classified output by following the agent, with each step explained in plain words.

**Why this priority**: the issue's first item. The six skills carry the detail; the overview must carry the conversation so a user can always start there.

**Independent Test**: read the overview and, for each of the six stages, find its one-line purpose, the question(s) to put to the user, the thing to show, the approval it waits for and the next-stage line; the drift test checks each stage has them.

**Acceptance Scenarios**:

1. **Given** the overview is loaded, **When** the agent reaches any stage, **Then** the overview says in plain words what that stage does and why the user should care, which decisions are the user's, and what the user must say before moving on.
2. **Given** the user is unsure which skill to call, **When** the agent follows the overview, **Then** the answer is always "call `/goldlabel`; it will check what you have and tell you the next skill", and the overview says so as the first instruction in the procedure.
3. **Given** the user calls a stage skill directly, **When** the stage's entry check passes, **Then** nothing in the overview changes the stage's own behaviour, and the stage's "Next" line still names the next skill.

---

### User Story 3 - The agent teaches the labelling and review page, and sends every revision through it (Priority: P1)

The overview, and `goldlabel-tune` where the user labels or reads disagreements, tell the agent what the labelling page does and how to start it: `goldlabel label` in a terminal (it lists datasets, samples and rows; opens a row by id; labels the pending rows; lets a person revise a label or a note; lists each evaluation with its disagreements and a STALE flag), and `gl.label(sample, taxonomy)` from the notebook (it joins the page when it is already running). When the user says a gold label is wrong, the agent says that people change it in the page, tells them how to open it, and offers to re-evaluate afterwards (an evaluation made before a revision shows as STALE). The agent never proposes any other way to change a gold label, and never edits a gold file.

**Why this priority**: the tester was invited to change labels and the skill had no way to support it; the gold rule makes the page the only route, so the skills must name it.

**Independent Test**: the drift test checks the overview names `goldlabel label`, `gl.label`, STALE and the page's jobs, and that no skill or reference offers a gold edit; the gold-rule refusal trial (a human check, see Assumptions) asks an agent to fix a label and expects it to point at the page and refuse to edit.

**Acceptance Scenarios**:

1. **Given** the user says a label looks wrong, **When** the agent responds, **Then** it tells them to revise it in the labelling page (command and notebook form), never says it will change it, and never mentions editing `gold.json`, polars, pandas or a cell as an option.
2. **Given** the user asks what the page can do, **When** the agent answers from the overview, **Then** the list matches the shipped page (datasets, samples, rows, jump to id, label pending, row editor, evaluations with disagreements, STALE).
3. **Given** the user has just revised labels, **When** the agent next evaluates, **Then** it tells them the earlier evaluation is STALE and that a new one is a new line in the log; it does not delete or rewrite the old one.
4. **Given** the user insists, "just fix them", **When** the agent responds, **Then** it refuses per the gold rule, offers the page and other help.

---

### User Story 4 - `goldlabel-tune` reads disagreements from the page, not only from code (Priority: P2)

At the disagreement-reading step of `goldlabel-tune`, the agent offers the user the page's evaluation view (each evaluation's disagreements and each row's labels and note) alongside `ev.disagreements_to_polars()`, so the person who labelled the rows can see a disputed row and decide whether the label or the prompt is wrong. If the person revises a row, the agent says the evaluation is STALE and evaluates again, comparing which rows flipped as it already does for prompt changes.

**Why this priority**: it makes the page part of the tuning loop, which is where label disputes surface; the loop works without it, so it ranks below the entry point and the revision route.

**Independent Test**: the drift test checks `goldlabel-tune` mentions the page's evaluation view and STALE at the reading step and keeps every existing step, entry and exit check.

**Acceptance Scenarios**:

1. **Given** a dev evaluation with disagreements, **When** the agent reads them with the user, **Then** it offers the page's view of that evaluation and says who decides on a label (the person, never the agent).
2. **Given** the user revised rows in the page, **When** the agent continues, **Then** it re-evaluates the dev sample and treats the comparison as a new evaluation, not as an edit of the old one.
3. **Given** the held-out test sample, **When** the agent offers the page, **Then** it does not use the test sample's disagreements to guide edits (Principle VI stays: the page may show them, the agent does not read them to tune).

---

### User Story 5 - The three copies of the instruction text agree (Priority: P2)

`docs/agent-instructions.md`, `.kiro/steering/goldlabel.md` and the text `goldlabel install` writes (`POINTERS` in `cli.py`) say that `/goldlabel` is the place to start, that it checks progress first, and that label revision goes through the page, in one wording, and the tests fail when they drift.

**Why this priority**: agents that never load skills see only these.

**Independent Test**: the existing docs drift test plus a new assertion that the "start here and check progress" and "revise in the page" bullets are present and equal in the three places.

**Acceptance Scenarios**:

1. **Given** the three files, **When** the tests run, **Then** they fail if any of the bullets differs or is missing.

### Edge Cases

- A notebook with cells out of order, or with a stage's calls in a different cell than expected: the check reads the calls, not cell positions.
- A notebook that has been run partly (a call exists but the cell failed, or its output is empty): the agent reports it as "present but not confirmed to have run" and asks.
- The storage folder holds datasets for more than one corpus (`gold-<name>.json`): the agent asks which one the user is working on before reading evaluations.
- Stage evidence exists only in `.goldlabel/` (a gold file and evaluations) and the notebook is missing: the agent reports what the files show and says the notebook is the record that matters; it does not rebuild one without the user's yes.
- The notebook contains something other than goldlabel calls (a guard, a helper, a side file): the progress check reports it and offers to remove it as an optional clean-up under the existing code rule; it never deletes it unasked.
- The user labelled rows in a pre-015 format that is no longer read: the agent says so and does not convert it.
- A different agent (Codex, Copilot, Kiro) without a skill tool: the instruction block carries the same start-here and progress-check sentence, and the agent reads the overview file.
- The labelling page is not reachable (no browser, a remote agent): the agent says which command the user runs on their own machine and does not claim to have opened it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The overview skill MUST make "check what the user already has" its first step in the procedure, before any stage is started, and MUST say that `/goldlabel` is where a user starts whenever they do not know which skill to call.
- **FR-002**: The progress check MUST say what evidence each of the six stages leaves in a notebook, script or storage folder (the corpus object, the search-term variables, the taxonomy, the `get_candidates` call and `candidates.jsonl`, the classifier with gold and evaluations in `gold*.json` and `evals.jsonl`, the estimate, the full classification and any saved classifier), and which stage the user resumes at: the first with no evidence.
- **FR-003**: The progress check MUST report to the user what it found, stage by stage and naming the evidence, mark anything uncertain as uncertain, and wait for the user's confirmation before skipping any stage; evidence alone MUST NOT cause a skip.
- **FR-004**: The check MUST read only the user's notebook or script and the storage folder's file names and modification times; it MUST NOT modify, run or delete anything, MUST NOT open `gold*.json` or `evals.jsonl` (an evaluation line holds the disagreements' row text, gold labels and model reasoning, so counts cannot be read from it without reading user data; ask the user for counts, or point them to the page), and MUST NOT read a key, a database URL or a `.env`.
- **FR-005**: The overview MUST give, for each of the six stages, a one-line plain-words purpose, the decisions the user makes, what to show them, what the user must approve, and the closing "Next" line, so that an agent with only the overview can guide the whole sequence; the stage skills keep the detail and are unchanged in order, parts and rules.
- **FR-006**: The overview MUST include short guidance on how to talk the user through a step: say what the step is for, show the result, ask the decision that is theirs, wait, and say what comes next; plain words; one stage at a time; no jargon unexplained.
- **FR-007**: The overview MUST describe the labelling and review page in the jobs the shipped page has (datasets, samples and rows; jump to a row by id; label pending rows; revise a label or note; each evaluation's disagreements; the STALE flag), how to start it (`goldlabel label [NAME]` with its options from `goldlabel label --help`, and `gl.label(sample, taxonomy)`, with `force_open_ui=True`), that the notebook call joins a page already running, and that the page never shows a model's prediction while a person labels.
- **FR-008**: The overview and `goldlabel-tune` MUST state that every revision of a gold label or note goes through the page, MUST NOT mention any other way to change a gold label as an option, and MUST keep the gold rule text verbatim (`src/goldlabel/gold_rule.md` stays canonical; no reword).
- **FR-009**: `goldlabel-tune` MUST offer the page's evaluation view at its disagreement-reading step, say that a revised row makes earlier evaluations STALE so the sample is evaluated again (a new log line), and keep the held-out test rule unchanged.
- **FR-010**: `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md` and the instruction text in `src/goldlabel/cli.py` MUST carry the same new bullets (start at `goldlabel`, which checks progress first; revise through the page) in one wording.
- **FR-011**: `tests/test_skill_stages.py` MUST fail when the progress check is absent, when it lacks any stage's evidence, when the overview omits `goldlabel label`, `gl.label` or STALE, when `goldlabel-tune` omits the page at the reading step, or when any skill or reference offers a gold edit; its existing assertions stay, and `tests/test_docs.py`/`tests/test_cli.py` keep the three copies in sync.
- **FR-012**: The change MUST NOT add a library function, a console command, a flag or a way to set a gold label (constitution Principle I); it changes agent-facing text and tests only.
- **FR-013**: The overview MUST stay within the code rule: every Python example in a skill or reference is goldlabel calls only and passes `test_examples_are_goldlabel_calls_only`.
- **FR-014**: Where the issue's text and the shipped behaviour differ (`gold.jsonl` versus `gold.json`), the skills MUST use the shipped behaviour.

### Key Entities

- **Progress check**: a read-only step at the start of the overview: input is the user's notebook or script and the storage folder; output is a per-stage report (done with evidence, unsure, not started) and a proposed resume stage.
- **Stage evidence**: the call, variable or file that shows a stage was done; listed in the overview, one line per stage.
- **Labelling and review page**: the page started by `goldlabel label` or `gl.label`; the only place a gold label or note changes after it was written.
- **Instruction text**: the block in `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md` and `cli.py`, one text in three places.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer reading only the overview can say, for each of the six stages, its purpose, the user's decisions and the approval it waits for, with no omissions (checked against a six-row checklist).
- **SC-002**: Given three fixtures (empty folder; stages 1 to 3 done; all six done), a reader following the progress check names the right resume point in 3 of 3.
- **SC-003**: In an agent trial in Claude Code and one other agent (human check), a user who has a notebook with stages 1 to 3 done calls `/goldlabel` once and is offered `goldlabel-tune`, not `goldlabel-connect`, without asking for it.
- **SC-004**: In the gold-rule refusal trial, asking an agent to fix a gold label gets a pointer to the labelling page and a refusal in 3 of 3 phrasings tried, and no mention of editing a gold file.
- **SC-005**: The drift tests fail for each of: a removed progress check, a removed stage evidence line, a removed page mention in the overview or in `goldlabel-tune`, an added gold-edit instruction, and a differing instruction bullet in any of the three copies.
- **SC-006**: No existing test is weakened: the stage order, the four parts, the code rule, the gold-rule text and the other drift tests pass unchanged.

## Assumptions

- The page and CLI described are those of feature 015 as shipped; this feature teaches them and does not change them.
- Reading a notebook is done by the agent with its own file tools; the library gets no helper for it (a progress helper would be code nobody asked for).
- The progress check is guidance for the agent, not a verdict: the user's confirmation decides where the work resumes.
- Stage evidence is judged from goldlabel calls only, consistent with the rule that a notebook holds goldlabel calls and nothing else.
- The human checks (agent trial, gold-rule refusal trial in each agent) are recorded in `AGENTS.md` for Chris, as in 009, 011 and 015; an agent never fakes them.
- `/ponytail-review` runs on this spec, the plan and the tasks before implementing, and `/ponytail-review` plus `/ponytail-debt` on the diff; the user has not waived it for this feature.

## Deliberately skipped

- A library function or command that reports progress (`goldlabel status`): the agent reads the notebook; a status command would be stored state the constitution forbids.
- Changing the order, the four parts or the entry checks of the six stage skills, or merging the overview into them.
- Any new way to edit a gold label, including a "fix labels" helper or an escape hatch in a skill; the issue forbids it and so does Principle I.
- Changes to the labelling page, the CLI options, `gold.json` or `evals.jsonl`.
- Auto-resuming without the user's confirmation, and auto-cleaning a notebook the check finds off the code rule.
- Rewording the gold rule.

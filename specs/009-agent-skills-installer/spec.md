# Feature Specification: Workflow agent skills and a one-command installer

**Feature Branch**: `claude/agent-skills-harness-spec-ht497z` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-10-30

**Status**: Draft

**Input**: User description: "Improve the agent harness setup: a set of workflow agent skills (data store setup/connection check, keyword/regex/seed generation and data shaping, agent-assisted taxonomy building loop, candidate generation and inspection, gold-labelling advice and dev-set prompt tuning without ever writing gold labels, test re-draw / fold into dev, cost estimate and full classification) installable in Claude Code, Codex, Copilot CLI and Kiro and manually in other agents, plus a single CLI entrypoint that installs the skills for the user's harness."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install the skills for my agent with one command (Priority: P1)

A user has `goldlabel` installed and uses Claude Code, Codex, GitHub Copilot CLI or Kiro. They run one
command, name their agent (or let it default), and the goldlabel skills are in the place that agent
reads them from, with the gold rule in front of the agent from the first message. They do not copy
folders, edit manifests or look up each tool's install syntax.

**Why this priority**: today the user must find the right install recipe per tool, three of which the
README marks unverified. Without this the skills in the other stories never reach an agent.

**Independent Test**: in an empty temporary project and an empty temporary home directory, run the
command once per agent and check the files it reports exist where that agent's documentation says
it reads skills; run it again and check nothing changes.

**Acceptance Scenarios**:

1. **Given** an empty project, **When** the user installs for each of the four agents, **Then** every
   workflow skill is present for that agent at the location its documentation names (project or
   user-wide, as asked), and the command prints each path it wrote and what to do next (for example
   reload skills or restart the agent).
2. **Given** a project where Codex and Copilot CLI both read the same shared skills folder, **When**
   the user installs for both, **Then** the skills are written once, not twice, and the output says
   so.
3. **Given** skills already installed, **When** the user runs the command again, **Then** nothing
   changes and it says "already up to date"; **Given** an installed skill whose files differ from
   the shipped ones, **Then** the command refuses to overwrite it and says how to force.
4. **Given** the user installs for Kiro, **When** it finishes, **Then** the gold rule is also in Kiro's
   always-included steering location, and the output states that Kiro custom agents must list the
   skills in their own resources (the command does not edit the user's agent files).
5. **Given** an agent that is not one of the four, **When** the user asks for a plain directory
   target, **Then** the skills are written to that directory in the common skill-folder layout, and
   the output tells the user to point their agent at it.
6. **Given** no network and no repository checkout (only the installed package), **When** the user
   runs the command, **Then** it works.

---

### User Story 2 - An agent takes me from the data to a first set of candidates (Priority: P1)

A user tells their agent what they want to analyse and where the data is. The agent connects to the
data store and confirms the connection works, helps reshape the data into the form the library
reads if it is not already, asks whether there are embeddings, and proposes keywords, regular
expressions or seed phrases accordingly, which the user edits and approves. The agent then runs
candidate generation and shows the user what came back, which phrases bring in what, and whether
the top items are what the user meant.

**Why this priority**: the workflow cannot start without a working corpus and a first candidate
list, and these are the steps where users get stuck on connection strings, formats and bad seeds.

**Independent Test**: with a fake database and a small local file (no real service), follow each
skill's steps by hand against the fixtures and check the calls in its examples run and the checks it
prescribes (connection check, column check, first rows) catch a deliberately broken input.

**Acceptance Scenarios**:

1. **Given** a database, an S3 vector index or a file, **When** the agent follows the connection
   skill, **Then** it confirms the connection and the text and id columns work before searching, and
   a database URL or key is read from an environment variable and never typed into a file or the
   chat.
2. **Given** a corpus with no embeddings, **When** the agent proposes a search, **Then** it proposes
   keywords or regular expressions, not seeds; **Given** embeddings, **Then** it offers seeds and
   says which embedder the corpus was built with.
3. **Given** data that is not in a readable shape (wrong column names, a nested file, a vector
   column in a CSV), **When** the user asks for help, **Then** the agent writes a small, reviewable
   transform that leaves the original file untouched and does not drop or repair rows silently.
4. **Given** a candidate list, **When** the agent inspects it, **Then** it reports the count, the
   spread, which seeds or terms bring in the items, and a sample, and recommends rewording a seed or
   term rather than touching the classifier when the items are junk.

---

### User Story 3 - An agent and I build the taxonomy together by reading the corpus (Priority: P1)

Before any classifier exists the user and the agent work out what the labels should be. The agent
searches and reads the corpus on its own (keywords, seeds, random samples, near-misses), reports
what kinds of items it finds, and proposes labels with one-or-two-sentence descriptions and where
the lines between nearby labels fall. The user can stay out of it and approve at the end, or go back
and forth: question a label, ask for more examples of a boundary, merge or split labels. The result
is a taxonomy the user approves.

**Why this priority**: the taxonomy decides what every later number means, and users usually do not
know the right labels until they have read the data. This is the step the user asked to be
agent-driven but optionally interactive.

**Independent Test**: run the skill's loop by hand over the sample corpus; check that it ends with a
taxonomy file that loads, that every label description came from a step the user approved, and that
nothing it wrote is in the gold file.

**Acceptance Scenarios**:

1. **Given** a brief and a corpus, **When** the agent runs the loop unattended, **Then** it reads
   samples and search results, writes up what it found, proposes a taxonomy, and stops for approval
   before saving it; nothing is final until the user says so.
2. **Given** the user wants to take part, **When** they ask about a label or a boundary, **Then** the
   agent fetches more items for that question and revises the proposal, one change at a time.
3. **Given** the agent has sorted items in its head while exploring, **When** the taxonomy is saved,
   **Then** those sortings are notes in the conversation or a notes file, never rows in the gold
   file, never counted as a score, and never used as labelled examples that the classifier is later
   scored on.
4. **Given** the user picks `single` or `multi` labels, the similarity cutoff, or the label
   descriptions, **When** the agent reaches that point, **Then** it asks and does not decide.

---

### User Story 4 - An agent helps with gold, tuning and the test split without labelling (Priority: P1)

Once there is a classifier the agent advises on the gold set (how many rows, which split, whether
each label has enough, which rows to draw), opens the labelling page for people to label, runs
evaluations on the dev split, reads the disagreements, proposes one prompt or description change at
a time and re-runs. When the user says the prompt is final, the agent evaluates the test split once.
If that score is too low and the user wants to keep working, the agent, after an explicit yes from
the user, folds the spent test rows into dev (their labels untouched) and draws a fresh test split
for people to label, so the new test split has never guided an edit.

**Why this priority**: tuning against human labels is the point of the library, and the gold rule
makes it the step an agent is most likely to be asked to shortcut. This story is also where the test
split stops being "evaluate once and live with it" (see the constitution amendment below).

**Independent Test**: in the end-to-end fixture (simulated human labelling over HTTP), run the
tuning loop with a stub model, fold the test split, draw a new one, and check: labels, text, ids
and who-labelled of every folded row are byte-identical afterwards, only the split changed, the
fresh test rows are pending until a person labels them, and the eval log shows the first test split
was spent.

**Acceptance Scenarios**:

1. **Given** a request to "just label a few rows", **When** an agent with these skills gets it,
   **Then** it refuses, explains the rule, and offers the labelling page, more seeds, a better prompt
   or reading the disagreements (the existing human trial is the check).
2. **Given** a dev evaluation, **When** the agent proposes a change, **Then** it changes one thing,
   says what it expects, shows which rows flipped, and warns before a run that makes live model calls
   on a large dev split.
3. **Given** the first test evaluation scores below the target, **When** the user asks to keep
   iterating, **Then** the agent explains that the test rows are now spent, asks the user for an
   explicit yes, folds them into dev, draws a fresh test split, and has people label it before any
   further test evaluation.
4. **Given** the user has not said yes, **When** the agent could fold, **Then** it does not.
5. **Given** a prompt with worked examples, **When** the agent adds an example, **Then** it checks
   the example is not a row in the dev or test gold set, because scoring on a row the prompt quotes
   is not a measurement.

---

### User Story 5 - An agent estimates the cost and runs the full classification (Priority: P2)

When the user is happy with the score the agent shows the estimate (calls, cost, time, and `cost ?`
with a warning when the price is unknown), asks whether to spend the money, runs the full
classification with a spending limit, saves the classifier, and tells the user where the output is.

**Why this priority**: it finishes the workflow, but the library already enforces the estimate and
the cost limit; the skill adds the order of steps and the asking.

**Independent Test**: run the skill's steps with a stub model and check the estimate is shown before
the run, the run carries a cost limit, and an unknown price refuses rather than showing zero.

**Acceptance Scenarios**:

1. **Given** a finished prompt, **When** the agent reaches the full run, **Then** the estimate is
   shown first and the run does not start until the user says yes.
2. **Given** an unknown price, **When** the estimate is shown, **Then** it reads `?` with a warning,
   never `$0`.

---

### User Story 6 - Use the skills in an agent that is not one of the four (Priority: P3)

A user of another agent (Cursor, Gemini CLI, any agent that reads `SKILL.md` folders or only an
instruction file) can install the skills by copying one folder, or paste one block into the
agent's instruction file, and follow a README section that says exactly that.

**Independent Test**: following only the README's manual section, copy the folder into a temporary
agent directory and check each skill's front matter is valid under the shared skill format and the
gold rule is verbatim in each.

**Acceptance Scenarios**:

1. **Given** the README, **When** a user follows the manual section, **Then** they end with the same
   skill folders the command writes, with no step that needs the command.

---

### Edge Cases

- A skills folder exists but is a symlink, or is read-only, or the home directory is unset: the
  command names the problem and writes nothing.
- The user passes an agent name the command does not know: it lists the valid names and exits
  without writing.
- The user installs project-level outside a project (no repository marker): it installs into the
  current directory as asked and says where that was.
- The user installs for all four agents: shared folders are written once; each agent's own folder
  once.
- Two skills' text disagree (for example on the order of steps): a test fails, because the workflow
  text is a single source of truth shared by the skills.
- The agent is asked, mid-taxonomy, to "label" some items so the classifier can learn: it refuses;
  taxonomy examples are notes, gold is labelled by people.
- The agent is asked to fold the test split without having evaluated it (nothing spent): the fold
  refuses, because there is nothing to retire.
- The test split has pending (unlabelled) rows when the fold is requested: it refuses and says to
  finish labelling first.
- A connection string pasted into the chat by the user: the agent tells them to use an environment
  variable and does not copy it into any file.

## Requirements *(mandatory)*

### Functional Requirements

**Skills**

- **FR-001**: The repository MUST ship a set of workflow skills, one per stage the user named,
  each a folder with a `SKILL.md`: (1) connect to the data store, confirm it works, and shape the
  data; (2) generate keywords, regular expressions or seed phrases; (3) build the taxonomy by reading
  the corpus; (4) run and inspect candidate generation; (5) gold-labelling advice and the dev-split
  evaluation and prompt-tuning loop, including the test split and the fold; (6) estimate the cost,
  run the full classification and save the classifier. The existing overview skill stays as the
  entry point that names the others. The plan MUST say whether stages 1-2 and 5 split or merge
  further; the stage list is what is required, not the folder count.
- **FR-002**: Every skill MUST carry the canonical gold rule verbatim and MUST fail the drift tests
  when its copy differs (extending the existing skill drift test; the rule text is not reworded and
  not hand-copied).
- **FR-003**: Every skill's front matter MUST be valid for all four agents at once: a lowercase,
  hyphenated `name` equal to its folder name, a `description` within the shortest limit any of the
  four documents, and no field one of them rejects. Each description MUST say when to use the skill
  so the agent picks it without being told.
- **FR-004**: Each skill's code examples MUST use only public names of the library, checked by the
  existing drift test, and MUST show the library call before the explanation of why.
- **FR-005**: The connection skill MUST have the agent confirm the connection and the id and text
  columns before any search, name the optional extra needed (for example `goldlabel[pg]`) when an
  import fails, and keep every key and database URL in an environment variable.
- **FR-006**: The search-generation skill MUST choose keywords or regular expressions when the
  corpus has no embeddings and offer seeds when it does, ask the user for the brief first, and
  present everything it generates as a proposal the user edits.
- **FR-007**: The data-shaping help MUST produce a transform the user can read, never modify the
  source file in place, and never drop or repair rows silently (the library's "first bad row is
  named" behaviour is kept).
- **FR-008**: The taxonomy skill MUST describe a loop of agent-driven reading and searching of the
  corpus, an optional back-and-forth with the user, and a stop for the user's approval before the
  taxonomy is saved. It MUST state that anything the agent sorts while exploring is notes, not gold.
- **FR-009**: Decisions the user owns (the brief, the seeds, `single` or `multi`, label
  descriptions, the similarity cutoff, the target score, whether to spend money, whether to fold the
  test split) MUST be asked by the skills, never decided.
- **FR-010**: The tuning skill MUST keep the existing rules: tune on dev, change one thing at a
  time, never read test disagreements to edit the prompt, show the estimate before a full run.
- **FR-011**: The tuning skill MUST check that any example quoted in a prompt is not a row of the
  dev or test gold set.
- **FR-012**: The cost skill MUST show the estimate and get an explicit yes before the full
  classification, pass a cost limit to the run, and show an unknown price as `?` with a warning.

**Fold and fresh test split**

- **FR-013**: The library MUST provide one operation that moves already-labelled test rows to dev
  and changes nothing else about them (text, id, labels, who labelled them and when stay as they
  were). It MUST refuse when the test split has pending rows or has never been evaluated, and it
  MUST be recorded so the evaluation log shows that a test split was spent and how many rows moved.
- **FR-014**: The skills MUST only call that operation after the user has said yes in the
  conversation, MUST say what it does first, and MUST then draw a fresh test split that people
  label; the fresh split MUST NOT be evaluated until every row is labelled.
- **FR-015**: A test MUST prove the fold leaves every label, text and id byte-identical and that no
  code path in the repository sets a label other than the labelling server and `import_rows`.

**Installer**

- **FR-016**: The package MUST provide one command with one entry point for installing the skills,
  with a target for each of Claude Code, Codex, GitHub Copilot CLI and Kiro, a plain-directory
  target for any other agent, project or user-wide scope, and a way to list what it would write
  without writing.
- **FR-017**: For each of the four agents the command MUST write to the location that agent's own
  documentation names (recorded with the documentation links in the plan), write a folder shared by
  two agents once, and print every path written and the next step for the user.
- **FR-018**: The command MUST be idempotent: unchanged files stay unchanged, an installed skill
  whose files differ from the shipped ones is not overwritten without an explicit force, and a
  failure part-way leaves no half-written skill folder.
- **FR-019**: For Kiro the command MUST also install the always-included steering file carrying the
  gold rule and MUST tell the user that custom agents list skills in their own resources; it MUST
  NOT edit the user's agent configuration files.
- **FR-020**: The command MUST work from the installed package alone (no network, no checkout), and
  the skills it installs MUST be the same files that ship in the repository's plugin layout; a test
  MUST fail if the two diverge.
- **FR-021**: The command MUST NOT run git, load a `.env`, read or write a keyring, or start
  the labelling page, and importing the library MUST NOT import it (import stays free of I/O).
- **FR-022**: The command MUST NOT be able to write, edit or import a gold label or gold file, and
  its only writes are the skill and steering files it reports.
- **FR-023**: The README MUST lead with the command for the four agents and give a short manual
  section for any other agent; install recipes for the four agents that the command replaces, and
  that are marked unverified, MUST be removed from the README rather than left beside it. The
  existing plugin manifests stay.

**Constitution and documents**

- **FR-024**: The constitution MUST be amended (MINOR, through `/speckit-constitution`, with the
  user's approval) to (a) allow the fold of a spent test split and a fresh test split, on the
  user's explicit yes, in Principle VI, and (b) record the new console command in the stack and
  agent-packaging sections. Principle I MUST NOT be changed, weakened or reworded, and the canonical
  gold rule text MUST NOT change. `AGENTS.md`, `README.md`, `docs/agent-instructions.md` and the
  Kiro steering file are updated in the same change where they say "no console script" or "the test
  split is evaluated once".

### Key Entities

- **Workflow skill**: a folder with `SKILL.md` (and optional references) for one stage of the
  analysis; carries the gold rule; lists the decisions the user owns at that stage.
- **Harness target**: one of Claude Code, Codex, Copilot CLI, Kiro, or a plain directory; maps to a
  project location, a user-wide location and any extra file the harness needs (Kiro steering).
- **Install report**: what the command printed: paths written or skipped, why, and the next step.
- **Spent test split**: test rows that have been evaluated; they stay human-labelled and, after the
  fold, belong to dev.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user goes from "goldlabel installed" to "skills available in my agent" with one
  command and no manual file copying, for each of the four agents, in under one minute.
- **SC-002**: Running the command twice in a row changes zero files the second time, for all four
  agents and both scopes.
- **SC-003**: 100% of the shipped skills carry the exact gold rule and valid front matter for the
  four agents; the drift tests fail on any mismatch.
- **SC-004**: In each of the four agents, asked to "just label a few gold rows", the agent refuses
  in every trial (a human trial; agents report that it has not been run until a person runs it).
- **SC-005**: Following only the skills, a new user reaches a saved classifier from a fresh corpus
  (file, database or S3 vectors) without needing to read the README, on the sample corpus with a
  stub model in the end-to-end test.
- **SC-006**: After a fold, 100% of folded rows keep identical labels, text, ids and labeller; the
  fresh test split has 0 labels until a person labels it.
- **SC-007**: A full classification never starts without a shown estimate and a user yes in any
  skill's instructions, and never shows `$0` for an unknown price.
- **SC-008**: The README's install section has no step marked unverified for the four agents.

## Assumptions

- Skill locations as documented (checked 2026-10-30; the plan records the pages and re-checks them):
  Claude Code reads `.claude/skills/` and `~/.claude/skills/`; Codex reads `.agents/skills/` (from
  the working directory up to the repository root) and `~/.agents/skills/`; Copilot CLI reads
  `.github/skills/`, `.claude/skills/` and `.agents/skills/` in a project and `~/.copilot/skills/`
  and `~/.agents/skills/` for the user; Kiro reads `.kiro/skills/` and `~/.kiro/skills/`, with its
  steering in `.kiro/steering/`. A custom Kiro agent does not load skills unless listed.
- All four read the shared `SKILL.md` folder format, so one set of skills serves all of them.
- Existing third-party installers do not cover all four agents reliably: the Node `skills` CLI needs
  Node and its documented Codex path differs from a Python port's; a Python library covers only
  Codex and Claude Code. The plan decides this with the evidence; the default is the standard
  library (copying a handful of folders to known paths) and no new dependency, which the plan's
  complexity table must justify if it chooses otherwise.
- The command is run as `goldlabel ...` after installing the package, or without installing it
  first through `uvx`; the exact subcommand name is the plan's.
- The agent runs the library's own functions in the user's notebook or script; the skills do not
  add new library features other than the fold in FR-013.
- A person reads and approves the taxonomy, the target score and the money; "optional back and
  forth" means the user may leave the loop to the agent, not that the agent may skip approval.
- Installing the plugin in each agent and running the gold-rule refusal trial stays a human task.

## Deliberately skipped *(Ponytail)*

- A skills registry, remote skill catalogue, versioned upgrade channel or `update` command:
  re-running the install is the update.
- An uninstall command: delete the folders the install report listed.
- Editing the user's agent files (Kiro `.kiro/agents/*.json`, `AGENTS.md`, `CLAUDE.md`): the command
  prints what to add instead.
- Agents beyond the four plus a plain directory (Cursor, Gemini CLI, Windsurf and the rest).
- A new dependency for installing, unless the plan finds a library that covers all four reliably.
- Enforcing "no prompt example is a gold row" in library code: the skill asks the agent to check.
- Interactive prompts or a terminal UI in the installer: flags only.
- A library helper that turns agent exploration notes into labels of any kind. There is none, by
  design.
- Skills for tasks outside the pipeline (writing the story, charts of the results).

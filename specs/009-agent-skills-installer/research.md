# Research: Workflow agent skills and a one-command installer

Facts checked on 2026-10-30 against the pages linked; re-check before the release.

## R1. Where each agent reads skills

**Decision**: write to these folders (project / user-wide), one set of `SKILL.md` folders for all.

| Agent | Project | User-wide | Source |
|---|---|---|---|
| Claude Code | `.claude/skills/` | `~/.claude/skills/` | [Claude Code skills](https://code.claude.com/docs/en/skills) |
| Codex | `.agents/skills/` (cwd up to repo root) | `~/.agents/skills/` | [Codex skills](https://developers.openai.com/codex/skills) (redirects to learn.chatgpt.com/docs/build-skills) |
| Copilot CLI | `.github/skills/`, `.claude/skills/`, `.agents/skills/` | `~/.copilot/skills/`, `~/.agents/skills/` | [GitHub: add skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills) |
| Kiro | `.kiro/skills/` | `~/.kiro/skills/` | [Kiro skills](https://kiro.dev/docs/skills/) |

Copilot is installed into `.agents/skills/` (and `~/.agents/skills/`), which Codex also reads, so
installing for both writes one folder. Kiro steering: `.kiro/steering/` and `~/.kiro/steering/`
([Kiro steering](https://kiro.dev/docs/steering/)). Kiro custom agents load no skills unless the
agent lists `skill://.kiro/skills/*/SKILL.md` in `resources`; the default agent loads them.

Front matter that all four accept: `name` (required, lowercase letters, digits and hyphens, at most
64, must equal the folder name for Kiro) and `description` (required, at most 1024 characters for
Kiro). Copilot also documents `license` and `allowed-tools`; Kiro lists `license`, `compatibility`
and `metadata`. Shipping only `name` and `description` is safe in all four.

**Alternatives**: `.github/skills/` for Copilot (rejected: a separate copy for no gain); symlinks
between agent folders (rejected: Windows and copy-based tooling).

**Not verified**: the Copilot `copilot skill add` and `gh skill install` commands (read once, not
run); that Codex picks up `~/.agents/skills` in a real session; Kiro `skill://` glob in a real
custom agent. These are human checks (Constitution "Needs a human").

## R2. Use a library for the installing?

**Decision**: no. `argparse` plus `shutil`/`os.replace`, about 120 lines.

| Candidate | Finding | Why not |
|---|---|---|
| [`npx skills`](https://github.com/vercel-labs/skills) (vercel-labs, MIT) | Covers ~75 agents incl. all four; paths in `docs/agents.md`; installs from a git repo or local path | Needs Node 22.20+, installs from a source tree not a wheel; Kiro still needs manual `resources` |
| [`skillsmd`](https://pypi.org/project/skillsmd/) (PyPI, MIT, 0.1.0, beta) | Python port of the above | CLI only (no documented API); Codex project path `.codex/skills/` contradicts Codex's `.agents/skills`; single maintainer |
| [`agent-skill-installer`](https://github.com/omry/agent-skill-installer) (MIT, 0.4.0, alpha) | Library with API, installs bundled skills from a wheel | Codex and Claude Code only; pulls `textual`, `omegaconf`, `packaging` (this repo bans Textual) |

Writing four paths and a byte comparison is less code than adapting any of them and has no
dependency. `shortcut:` comment in `cli.py`: the agent table is a literal; upgrade to a library when
more than these four agents are wanted.

## R3. Shipping skills in the wheel and the plugin

**Decision**: canonical skills live in `src/goldlabel/skills/`; the wheel includes them as package
files (`gold_rule.md` is already shipped that way, so files under the module directory are included
by `uv_build`; the task proves it by listing the wheel). Claude Code's plugin manifest is pointed
at them: `"skills": ["./src/goldlabel/skills"]` ([plugins reference](https://code.claude.com/docs/en/plugins-reference):
path must start with `./`, resolve inside the plugin root and exist; it adds to the default
`skills/` scan, which is then empty/absent). `claude plugin validate .` is run in the quickstart.

**Alternatives**: keep root `skills/` and copy into the package at build time (rejected: needs a
build hook `uv_build` lacks); two committed copies with an equality test (rejected: duplicate of
~40 KB and a second place to edit); a symlink (rejected: the docs do not say whether plugin caching
keeps symlinks, and Windows).

**Risk**: the `npx skills` and Kiro/Codex plugin routes that auto-discover `skills/` at the repo
root no longer find it (vercel's discovery also reads `.claude-plugin` manifests per its docs, so it
should still work). The README stops advertising those routes; the command is the supported path.

## R4. Fold of a spent test split

**Decision**: `Gold.fold_test()` as in the plan's Design. The log needs a fold record because
`EvalLog` counts "test split evaluated N times" and a fresh test split must not inherit the old
count. `eval_log()` keeps evaluation rows and fold events apart so the polars/pandas table shape is
unchanged. Rationale for allowing it: a test split that has been scored and then used to decide to
keep tuning is a second dev set; relabelling it as dev says so honestly, and the fresh split has
never guided an edit. Alternative (spec user choice): a method the user runs; rejected by the user.

## R5. Taxonomy loop and the constitution

Agents reading the corpus and proposing labels does not violate any principle: Principle I forbids
writing a gold label, not reading items; Principle VI makes label descriptions a user decision, which
the loop's approval stop honours. No amendment is needed for the loop. The risk is leakage, not
legality: items the agent hand-sorts must not become labelled examples in the prompt that are also
in gold (FR-011), and exploration notes must not be written to any gold path (FR-008).

## R6. Amendments

- Principle VI: add that after the test split is evaluated and the user wants to keep tuning, the
  user may say yes to `gold.fold_test()` and a fresh test split that people label; an agent MUST NOT
  fold without that yes. MINOR bump to 1.2.0.
- Stack and Agent packaging: one console command `goldlabel` (installer only), skills at
  `src/goldlabel/skills/`. `AGENTS.md` and the README drop "no console script" and the Layout line
  is updated.
- Principle I and `gold_rule.md`: not touched.

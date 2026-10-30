# Contract: `goldlabel install`

```
goldlabel install [AGENT ...] [--global] [--dir PATH] [--force] [--dry-run]
uvx goldlabel install claude        # without installing the package first
```

| Argument | Meaning |
|---|---|
| `AGENT` | one or more of `claude`, `codex`, `copilot`, `kiro`, `all`. None given: print the choices to stderr, exit 2. |
| `--global` | user-wide folders (`~/...`) instead of the current directory's. |
| `--dir PATH` | write the skill folders to `PATH` for any other agent; cannot be combined with `AGENT`. |
| `--force` | replace an installed skill whose files differ from the shipped ones. |
| `--dry-run` | print what would be written; write nothing. |

Folders (research R1). Project: claude `.claude/skills`, codex and copilot `.agents/skills`, kiro
`.kiro/skills` plus `.kiro/steering/goldlabel.md`. With `--global` the same names under the home
directory.

**Output** (stdout, one line each, plain text, no colour):

```
installed  .agents/skills/goldlabel            written
installed  .agents/skills/goldlabel-connect    up to date
...
installed  .kiro/steering/goldlabel.md         written
next (codex, copilot): codex: restart or type $ to see skills; copilot: run /skills reload
next (kiro): custom agents must list "skill://.kiro/skills/*/SKILL.md" in their resources
```

**Exit codes**: 0 everything written or up to date; 1 refused (a skill differs and no `--force`, the
folder is unwritable or is a symlink, unknown agent); 2 usage error. Refusal writes nothing for that
folder; other folders already done stay done and are reported.

**Never**: reads or writes a gold file, a `.env`, a keyring or git; edits `AGENTS.md`, `CLAUDE.md`
or `.kiro/agents/*`; makes a network call; prompts. Importing `goldlabel` does not import
`goldlabel.cli`.

**Atomicity**: each skill folder is copied to `<folder>/.<name>.tmp` and moved into place with
`os.replace`; on any error the temporary folder is removed.

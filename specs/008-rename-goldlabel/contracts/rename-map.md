# Contract: what the rename changes

The public surface after this feature. Everything not listed is unchanged.

| Surface | Old | New |
|---|---|---|
| Import package | `hunches` | `goldlabel` |
| Docs import alias | `hn` | `gl` |
| Distribution and extras | `hunches[s3\|pg\|rds\|local]` | `goldlabel[s3\|pg\|rds\|local]` |
| `__version__` source | `version("hunches")` | `version("goldlabel")` |
| Root directory env var | `HUNCHES_DIR` | `GOLDLABEL_DIR` |
| Default root | `.hunches/` | `.goldlabel/` |
| Postgres URL env var (default) | `HUNCHES_PG_URL` | `GOLDLABEL_PG_URL` |
| Postgres test URL (tests, CI) | `HUNCHES_TEST_PG_URL` | `GOLDLABEL_TEST_PG_URL` |
| Labelling function | `hunches.label` | `goldlabel.label` |
| Labelling module | `hunches._label` | `goldlabel._label` |
| Labelling page title / request header | `hunches: label` / `X-Hunches-Token` | `goldlabel: label` / `X-Goldlabel-Token` |
| New row stamp | `hunches-ui` | `goldlabel-ui` (legacy `hunches-ui` still read) |
| Evaluation-log version key | `hunches` | `goldlabel` |
| Skill dir and name | `skills/hunches`, `hunches` | `skills/goldlabel`, `goldlabel` |
| Kiro steering | `.kiro/steering/hunches.md` | `.kiro/steering/goldlabel.md` |
| Plugin and marketplace name | `hunches` (`hunches@hunches`) | `goldlabel` (`goldlabel@goldlabel`) |
| Repository URL in manifests | `https://github.com/cmhac/hunches` | `https://github.com/cmhac/goldlabel` |
| Gold rule text | "...of the hunches library", "`hunches.label`", "the hunches labelling page" | the same with `goldlabel` |

Not read any more, no fallback: `HUNCHES_DIR`, `HUNCHES_PG_URL`, `.hunches/`, `import hunches`.

Left as history, by design: `specs/001` to `specs/007`, `tests/fixtures/pre006/README.md`, git history.

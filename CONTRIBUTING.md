# Contributing

Thanks for contributing! This repo is a monorepo with three sub-projects — the DSH plugin only works alongside the Hub backend and Share Web viewer, so most changes touch more than one of them.

## Setup

Prerequisites: `uv`, `node`, `pnpm`, the `dsh` CLI, `curl`, `lsof`.

```bash
./scripts/dev.sh setup  # install all deps, build, and install the plugin into DSH
```

See the root [README](README.md) for the full quick start and service topology.

## Development loop

```bash
./scripts/dev.sh start  # run Hub + share-web + DSH Web together, with smoke tests
./scripts/dev.sh check  # re-run smoke tests against a running stack
```

Logs land in `$TMPDIR/dsh-artifact-hub-dev-*/`. Override ports and paths via `scripts/dev.env` (copy from `dev.env.example`).

## Testing

Run everything before opening a PR:

```bash
./scripts/dev.sh test
```

That runs, per sub-project:

| Sub-project | Tests | Typecheck | Build |
|---|---|---|---|
| `hub/` (Python) | `unittest` | `compileall` | — |
| `plugins/dsh-artifact-hub/` | vitest | `tsc` | tsdown |
| `apps/share-web/` | vitest | `tsc` | vite |

Individual commands are documented in each sub-project's README.

## Issues and specs

This repo tracks issues and specs as Markdown files under `.scratch/`, which is kept local by design — see the [issue-tracker conventions](docs/agents/issue-tracker.md):

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `spec.md`; implementation issues are numbered files under `issues/`, in dependency order
- Status lives on the `Status:` line of each issue

Triage labels and their meanings are defined in [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md).

## Before you change the domain

Read [`CONTEXT.md`](CONTEXT.md) for the canonical definitions of Artifact, Artifact Version, Share, and the storage modes — PRs should use these terms consistently. If your change contradicts a decision in [`docs/adr/`](docs/adr/), either work within it or propose a new ADR rather than silently diverging.

## Commit style

Keep commits focused; describe the why in the body when it isn't obvious. Match the existing code's style — comment density and naming included.

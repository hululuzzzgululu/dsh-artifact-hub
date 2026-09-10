# Documentation

Start with the root [`README.md`](../README.md) for what this project is and how to run it. This directory holds the deeper material.

## Map

| Path | What it covers |
|---|---|
| [`overview.md`](overview.md) | Full overview design: background, domain model, storage modes, API draft, architecture (Chinese) |
| [`deployment.md`](deployment.md) | Production deployment: Hub as a systemd service, Share Web + Nginx, plugin config, verification, ops |
| [`adr/`](adr/) | Architecture Decision Records — why the code is shaped this way |
| [`research/`](research/) | Background research notes |
| [`agents/`](agents/) | Conventions for AI-assisted work: triage labels, issue tracker, domain docs |

Sibling docs that live with their code:

| Path | What it covers |
|---|---|
| [`../CONTEXT.md`](../CONTEXT.md) | Domain glossary — canonical definitions of Artifact, Artifact Version, Share, etc. |
| [`../hub/README.md`](../hub/README.md) | Hub backend: HTTP API, configuration, SQLite/MySQL, migrations |
| [`../plugins/dsh-artifact-hub/README.md`](../plugins/dsh-artifact-hub/README.md) | DSH plugin: install, configuration, data flow |
| [`../apps/share-web/README.md`](../apps/share-web/README.md) | Share Web viewer: dev, build, supported formats |
| [`../deploy/nginx/README.md`](../deploy/nginx/README.md) | Nginx routing details for the public boundary |
| [`../deploy/systemd/artifact-hub.service`](../deploy/systemd/artifact-hub.service) | systemd unit template for the Hub service |

## ADRs

Decisions are recorded as short, numbered files. Read them before changing the areas they cover:

1. [Filesystem adapters for Local and NAS storage](adr/0001-filesystem-storage-for-local-and-nas.md)
2. [Database persistence behind repository adapters](adr/0002-database-repository-adapters.md)
3. [Separate database row identity from business identity](adr/0003-separate-row-and-business-identities.md)

## Language

The root README is bilingual: [`README.md`](../README.md) (English) and [`README.zh-CN.md`](../README.zh-CN.md) (简体中文). ADRs and the glossary are in English. The overview design and the sub-project READMEs are currently in Chinese; translation is welcome.

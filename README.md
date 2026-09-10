# Artifact Hub for DeepSeek Harness

[简体中文](README.zh-CN.md) | English

Artifact Hub turns the mutable files an agent generates during a DeepSeek Harness (DSH) session into immutable, shareable artifact versions — with a public link, decoupled from the session's lifetime.

```
Agent writes a file → you click [Share] → immutable version snapshot → share link → anyone views / downloads
```

## Why

During a DSH session, the agent produces files in the session workspace — SQL, HTML, Markdown, PDF, images, and more. Sharing one today means sharing the whole session, or downloading the file and re-sending it over IM or email.

Artifact Hub gives files an independent sharing lifecycle:

- **Share a file, not a session.** A shared link keeps working even after the original session is closed or cleaned up.
- **Immutable versions.** Sharing snapshots the file. If the agent later edits it, sharing again creates the next version — already-shared links never change.
- **Revocable, expiring links.** Every share can be revoked or given a deadline.
- **Safe preview.** A public viewer renders Markdown, code, JSON, images, PDF, and sandboxed HTML — untrusted agent HTML can never touch DSH.

## It's a stack, not a single plugin

The DSH plugin alone does nothing. It is one piece of a three-service system — plan to run all of them:

```
                         User
                          │
                 ┌────────┴────────┐
                 ▼                 ▼
               DSH             Share Web          ← what people see
                │                 │
                └───────┬─────────┘
                        ▼
                 Artifact Hub                  ← the brain
                        │
             ┌──────────┴───────────┐
             ▼                      ▼
          Database           Artifact Storage
                                  │
                           ┌──────┴──────┐
                           ▼             ▼
                         Local           NAS
```

| Component | Path | Role | Runtime |
|---|---|---|---|
| **Hub** | [`hub/`](hub/) | The backend. Owns artifacts, versions, shares, storage paths, checksums, tokens, and all lifecycle rules. FastAPI + SQLite (default) or MySQL. | Python service |
| **DSH plugin** | [`plugins/dsh-artifact-hub/`](plugins/dsh-artifact-hub/) | The in-DSH UI: the [Share] button next to files, and the Share Center sidebar. Forwards trusted workspace metadata to the Hub. | Inside DSH |
| **Share Web** | [`apps/share-web/`](apps/share-web/) | The public viewer at `/s/{token}`: preview, download, expiry/revocation notices. | Static site behind Nginx |
| **Deploy config** | [`deploy/`](deploy/) | The public boundary and service definitions: Nginx routing, systemd unit. | Nginx / systemd |

## Core model

```
Session File ──first share──▶ Artifact ──snapshot──▶ ArtifactVersion ──link──▶ Share
(mutable,                       (logical             (immutable,            (revocable,
 dies with session)              identity)             checksummed)           may expire)
```

- A file only becomes an **Artifact** when a user shares it. Normal agent output creates nothing.
- Each **ArtifactVersion** is an immutable snapshot; identical checksums reuse the existing version.
- A **Share** always points to a version — never to the live session file. One share per version; re-sharing replaces the link and invalidates the old one.

Terms are defined precisely in [`CONTEXT.md`](CONTEXT.md); the full design (Chinese) is in [`docs/overview.md`](docs/overview.md).

## Storage modes

Two filesystem modes; who moves the bytes differs, but the Hub always owns identity, versions, storage keys, and shares.

| | Local | NAS |
|---|---|---|
| Session file readable by Hub | Yes | Usually no (on the DSH machine) |
| Artifact storage | Hub's local disk | Shared NAS mount |
| Who copies the file | Hub | DSH plugin |
| File goes over HTTP | No | No |

**Local** — Hub and DSH can see the same filesystem. The plugin sends a reference; the Hub reads, checksums, and copies the snapshot itself.

**NAS** — Session files live on the DSH machine, but both sides mount the NAS. A two-phase protocol avoids an HTTP upload hop: the Hub `prepare`s a storage key, the plugin copies the file to the NAS directly, then the Hub `commit`s after validating it.

## Quick start

Prerequisites: `uv`, `node`, `pnpm`, the `dsh` CLI, `curl`, `lsof`.

One script drives the whole stack from the repo root:

```bash
./scripts/dev.sh setup  # install deps, build + install the plugin into the DSH profile
./scripts/dev.sh test   # tests, typecheck, and builds for all three sub-projects
./scripts/dev.sh start  # start Hub + share-web + DSH Web, with smoke tests
```

`start` runs all three services in the foreground (Ctrl-C stops them all):

| Service | Default URL |
|---|---|
| Hub | http://127.0.0.1:8000 |
| Share Web | http://127.0.0.1:5173 |
| DSH Web | http://127.0.0.1:3080 |

Copy `scripts/dev.env.example` to `scripts/dev.env` to override ports and paths. Then, inside a DSH session, click **[Share]** next to any generated file.

`dev.sh` is development-only. For a real deployment — the Hub as a systemd service, Share Web and the public API behind Nginx, TLS, and the plugin pointed at an internal Hub address — follow the [deployment guide](docs/deployment.md).

## Repository layout

```
├── hub/                    # Python backend (FastAPI, uv)
│   ├── src/api/            #   HTTP layer: routers, responses
│   ├── src/artifact_hub/   #   domain, services, storage, repositories
│   └── sqls/               #   schema
├── plugins/dsh-artifact-hub/
│   └── src/
│       ├── host/           #   trusted Host-side RPC (workspace resolution)
│       └── client/         #   Share button, Share Center UI
├── apps/share-web/         # public viewer (Vite SPA)
├── deploy/nginx/           # production routing config
├── docs/                   # design, ADRs, research, conventions
└── scripts/                # dev.sh and friends
```

## Security notes

- Share tokens are stored only as SHA-256 hashes; the raw token is returned exactly once, at creation.
- Management APIs are private to the DSH Host; the browser never supplies workspace roots or creator identity.
- Public content responses use `no-store`, `nosniff`, and CSP sandboxing; agent HTML renders in a sandboxed iframe, isolated from DSH cookies and APIs.
- Nginx excludes token-bearing URLs from access logs.

## Scope

**V1:** link sharing (`LINK` + view/download), Local and NAS storage, checksum-based version reuse, expiry, revocation, Share Center ("my shares"), public preview and download.

**Not yet:** object storage (S3/OSS/MinIO), presigned URLs, organization/user-targeted sharing, ShareGrant and "shared with me", auth, comments, editing.

## Documentation

- [`docs/`](docs/) — index of all documentation
- [`docs/overview.md`](docs/overview.md) — full overview design (Chinese)
- [`docs/adr/`](docs/adr/) — architecture decision records
- [`hub/README.md`](hub/README.md) — Hub API, configuration, database migration
- [`plugins/dsh-artifact-hub/README.md`](plugins/dsh-artifact-hub/README.md) — plugin install and data flow
- [`apps/share-web/README.md`](apps/share-web/README.md) — viewer development and build

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Issues and specs are tracked as Markdown files under `.scratch/`, which is kept local by design (see [the issue-tracker conventions](docs/agents/issue-tracker.md)).

## License

[MIT](LICENSE)

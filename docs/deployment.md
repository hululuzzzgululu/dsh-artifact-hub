# Deploying Artifact Hub

`scripts/dev.sh` is for local development only: it runs everything in the foreground, uses SQLite and dev servers, and assumes all three services share one machine with loopback access. This guide is the real thing — running the Hub as a service, publishing Share Web behind Nginx, and pointing the DSH plugin at it.

What is deployed where:

| Machine / host | Runs | Notes |
|---|---|---|
| Hub host | Artifact Hub (FastAPI), Nginx, MySQL (optional) | Owns `data/` (artifacts + database) |
| DSH host | DeepSeek Harness + the plugin | Must share a filesystem with the Hub (see below) |
| Public DNS | e.g. `share.example.com` → Hub host | The only internet-facing surface |

```
Internet ──▶ share.example.com (Nginx, port 443)
                │  /s/{token}            static share-web
                │  /api/public/shares/*  ──▶ Artifact Hub (127.0.0.1:8000)
                └─ everything else: 404 / private

DSH Host ──▶ http://hub-internal:8000  (management API, private network)
```

## 0. Choose a storage mode first

The plugin currently implements **Local** mode only. Local requires that the Hub can read the DSH session workspaces by absolute path — in practice the Hub and DSH run on the same machine, or the session workspaces sit on a shared mount both can see.

NAS mode (plugin copies to a shared NAS, Hub validates) is designed and implemented on the Hub side (`/api/shares/prepare` + `/api/shares/commit`), but the plugin does not drive it yet. If you need it, follow the design in [`overview.md`](overview.md) §12–16 and call the two-phase API yourself, or wait for plugin support.

## 1. Run the Hub as a service

On the Hub host, check out the repo (or your release artifact) and install Python dependencies:

```bash
cd /opt/dsh-artifact-hub/hub
uv sync --frozen
```

Create a dedicated user and data directory:

```bash
sudo useradd --system --home /opt/dsh-artifact-hub --shell /usr/sbin/nologin artifact-hub
sudo mkdir -p /var/lib/dsh-artifact-hub/artifacts
sudo chown -R artifact-hub: /var/lib/dsh-artifact-hub
```

Configuration is environment variables only:

| Variable | Production value | Meaning |
|---|---|---|
| `HUB_HOST` | `127.0.0.1` | Bind to loopback — Nginx is the only front door |
| `HUB_PORT` | `8000` | Matches the Nginx upstream |
| `HUB_BASE_URL` | `https://share.example.com` | **The public origin used to build share links.** Returned to users verbatim — set it to the public HTTPS origin, or links will point at the wrong host |
| `HUB_STORAGE_MODE` | `sqlite` or `mysql` | Database backend (`server` is a compatibility alias for `mysql`) |
| `HUB_DATABASE_PATH` | `/var/lib/dsh-artifact-hub/hub.sqlite3` | SQLite file (sqlite mode) |
| `HUB_ARTIFACT_ROOT` | `/var/lib/dsh-artifact-hub/artifacts` | Artifact storage root |
| `HUB_MYSQL_URL` or `HUB_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | — | MySQL connection (mysql mode); pool tuning via `HUB_MYSQL_POOL_SIZE`, `HUB_MYSQL_MAX_OVERFLOW` |

Install the systemd unit from [`deploy/systemd/artifact-hub.service`](../deploy/systemd/artifact-hub.service):

```bash
sudo cp deploy/systemd/artifact-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now artifact-hub
curl -fsS http://127.0.0.1:8000/healthz
```

> **Never expose port 8000 directly.** Management endpoints (`POST /api/shares`, revoke, listing) are trusted-internal; only `/api/public/shares/*` is meant for the internet, and only via Nginx.

## 2. Build and stage Share Web

```bash
cd apps/share-web
pnpm install --frozen-lockfile
pnpm build
sudo mkdir -p /usr/share/nginx/html/share-web
sudo cp -R dist/. /usr/share/nginx/html/share-web/
```

Keep the Hub and Share Web same-origin (`https://share.example.com`), so the SPA calls `/api/public/shares/*` on its own origin and Nginx proxies it. `VITE_API_BASE_URL` exists for split origins but is not recommended — it adds a CORS surface for no benefit.

## 3. Configure Nginx

Copy [`deploy/nginx/share-web.conf`](../deploy/nginx/share-web.conf) into your Nginx config, then adjust:

- the `artifact_hub` upstream if the Hub is not on `127.0.0.1:8000`,
- TLS (terminate at Nginx or your load balancer; the Hub speaks plain HTTP on loopback),
- the listen port / `server_name` for your domain.

```bash
sudo nginx -t && sudo systemctl reload nginx
```

The config already: serves `/s/{token}` as an SPA route, long-caches `/assets/*`, proxies **only** `/api/public/shares/*` to the Hub, and keeps token-bearing URLs out of access logs. Do not widen the proxied API surface without re-reading the security notes in the root README.

## 4. Configure the DSH plugin

On each DSH host, install the plugin and point it at the Hub's **internal** address:

```bash
dsh plugin --profile web add ./plugins/dsh-artifact-hub
```

| Variable | Production value | Meaning |
|---|---|---|
| `DSH_ARTIFACT_HUB_URL` | `http://hub-internal:8000` | Management API base (not the public share origin) |
| `DSH_ARTIFACT_HUB_CREATED_BY_ID` | e.g. `user-001` | Identity stamped on artifacts/shares created by this DSH host |
| `DSH_ARTIFACT_HUB_CREATED_BY_NAME` | e.g. `Alice` | Display name (defaults to the ID) |

Remember the Local-mode filesystem requirement: this host's session workspaces must be readable by the Hub at the same absolute path.

## 5. Verify

From an external machine:

```bash
# public metadata endpoint answers through Nginx
curl -fsS https://share.example.com/api/public/shares/not-a-real-token
# → expect a structured not-found, not a 502/403

# SPA route serves the viewer
curl -fsS https://share.example.com/s/anything | grep -o '<title>.*</title>'

# management API is NOT reachable from outside
curl -fsS -m 5 https://share.example.com/api/shares || echo "blocked (expected)"
```

Then create a real share from a DSH session and confirm the returned link opens in a browser, previews, and downloads.

## Operations

- **Back up the database and `HUB_ARTIFACT_ROOT` together.** They reference each other by `storage_key`; restoring one without the other yields broken shares.
- **Upgrades:** stop the service, `git pull` + `uv sync --frozen`, rebuild share-web, restart. Repository startup runs schema/data migrations automatically (legacy table renames, `created_by` splits); see `hub/README.md` for details. Back up before upgrading.
- **Disk growth:** artifact versions are immutable and never deduplicated across artifacts; `HUB_ARTIFACT_ROOT` grows monotonically. Monitor it.
- **Logs:** the Hub logs to stdout/stderr (→ journald under systemd). Nginx access logs exclude `/s/` and `/api/public/shares/` paths so tokens don't leak into logs.

## Known gaps

- No Docker image or compose file yet — deployment is build-from-source as described above.
- No release packaging/versioning; upgrades are git-based.
- NAS mode lacks plugin-side support (see §0).
- No authentication on management APIs beyond network privacy — keep the Hub port on a trusted network.

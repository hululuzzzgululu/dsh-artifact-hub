# Nginx deployment

`share-web.conf` demonstrates the V1 deployment boundary:

- `/s/{token}` is a static SPA route and falls back to `index.html`.
- `/assets/*` is a hashed, long-cache static asset.
- `/api/public/shares/*` is the only Hub API exposed by the public virtual host.
- Hub management endpoints remain private for the DSH Host plugin.
- URLs containing share tokens are excluded from Nginx access logs.

Build and stage the frontend:

```bash
cd apps/share-web
pnpm install --frozen-lockfile
pnpm build
cp -R dist/. /usr/share/nginx/html/share-web/
```

Copy or include `share-web.conf` in the Nginx configuration and update the `artifact_hub` upstream address for the target environment. Validate with `nginx -t` before reloading.

The public host serves link-based shares only; no organization identity header is accepted or forwarded.

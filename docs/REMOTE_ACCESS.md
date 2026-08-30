# Remote access architecture

The browser must never call a hard-coded `127.0.0.1` address in a public deployment. For an external visitor, that address points to the visitor's own machine.

## Recommended topology

```text
External user
    |
    | HTTPS
    v
Identity-aware gateway
    |
    | encrypted tunnel
    v
Local reverse proxy (127.0.0.1)
    |-- /          -> web UI
    |-- /api/*     -> LTX job API on 127.0.0.1:8787
    `-- /generated -> protected local outputs
                         |
                         v
                    LTX worker / NVIDIA GPU
```

## Production requirements

Before enabling external access:

1. Keep the Python API bound to `127.0.0.1`.
2. Use a managed HTTPS tunnel; do not forward a router port.
3. Require login or an invitation before job submission.
4. Apply per-user rate limits, quotas, and maximum resolution/duration.
5. Keep GPU concurrency at one until resource isolation is implemented.
6. Protect generated media URLs and remove outputs after a configured TTL.
7. Hide local paths, command output, and stack traces from API responses.
8. Record audit events without storing sensitive prompts longer than necessary.
9. Add job cancellation, timeouts, and disk-space safeguards.
10. Allow CORS only from the deployed web origin when using a separate API domain.

## Deployment modes

### Same-origin gateway — recommended MVP

Expose one HTTPS hostname. Route `/api/*` to the local API and all other paths to the web application. Set:

```env
LTX_USER_AUTH_ENABLED=1
LTX_PUBLIC_ORIGIN=https://ltx.example.com
LTX_INTERNAL_API_ORIGIN=http://127.0.0.1:8787
LTX_ALLOWED_ORIGINS=https://ltx.example.com
```

Relative API requests avoid browser localhost and CORS problems.

The repository includes this mode as a Cloudflare Tunnel configuration. See [Cloudflare setup](CLOUDFLARE.md).

### Separate API hostname

Browser account cookies are host-only. The UI deliberately uses relative `/api`
requests, not a separately configured public API origin. Use a trusted same-origin
server proxy if splitting the web and inference hosts. Do not share session cookies
or the privileged worker key with another project's browser. Server-to-server
callers continue to use the generic authenticated worker API.

## Not production-ready yet

The v1.2 code adds verified-email accounts, owner authorization and account quotas,
but activating it requires real SMTP delivery tests and migration of old static
media. Durable job history exists; a multi-user pending queue, public-scale abuse
controls and a full audit/admin UI are not included. Keep existing Access protection
until the [account deployment checklist](ACCOUNTS_AND_MODELS.md) has passed.

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
NEXT_PUBLIC_LTX_API_BASE=
NEXT_PUBLIC_LTX_MEDIA_BASE=
LTX_ALLOWED_ORIGINS=https://ltx.example.com
```

Relative API requests avoid browser localhost and CORS problems.

### Separate API hostname

Host the web UI separately and expose the local API through `https://api.example.com`. Set:

```env
NEXT_PUBLIC_LTX_API_BASE=https://api.example.com
NEXT_PUBLIC_LTX_MEDIA_BASE=https://api.example.com
LTX_ALLOWED_ORIGINS=https://ltx.example.com
```

This mode requires gateway authentication and strict CORS configuration.

## Not production-ready yet

The included Python service is a local worker bridge. It does not yet provide user accounts, durable multi-user queues, quotas, or authorization. Do not make it anonymously public.

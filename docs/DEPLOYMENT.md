# Deploying x12-tidy-web

Answers to [#26](https://github.com/tidyedi/web-facing/issues/26): where this
should live, and what "functional for all" actually requires.

## Should it go on the tidyedi site?

Yes — as its own thing, not bolted into a marketing page. It is a live server
process (FastAPI/uvicorn), so it cannot be a static page next to the rest of a
brochure site. Give it a subdomain and point a reverse proxy at the container:

- `tidy.tidyedi.com` or `repair.tidyedi.com` — a dedicated subdomain, cleanest.
- `tidyedi.com/repair` — a path the proxy routes to this container while the
  root serves the static site. Also fine; slightly more proxy config.

The marketing/docs site and this app stay separate deployments either way. Link
between them (that is [#27](https://github.com/tidyedi/web-facing/issues/27)).

## What "functional for all" requires

The app itself is ready — it is stateless, stores nothing, and the container in
`docker-compose.yml` already runs read-only, non-root, with all capabilities
dropped. What is missing is everything *around* it that a public URL needs.

### 1. A host to run the container

Anything that runs a container works. The image is a `python:3.12-slim` base
plus a small pure-Python venv (FastAPI, uvicorn, jinja2, x12-tidy); it idles in
well under 128 MB RAM. Low-effort options:

| Option | Notes |
| --- | --- |
| A small VPS (Hetzner, DigitalOcean, Fly.io) + `docker compose up -d` | Most control, ~$5/mo, you manage the OS. |
| Fly.io / Render / Railway from the `Dockerfile` | They terminate TLS and give you a URL; near-zero ops. |
| Cloud Run / Container Apps | Scales to zero; cold start ~2 s because x12-tidy is pip-installed into the image, not fetched at boot. |

The build needs network access to `github.com` (x12-tidy is installed from git)
and `git` in the builder stage — both already handled in the `Dockerfile`.

### 2. A reverse proxy in front (TLS + limits)

Never expose uvicorn directly. Put Caddy, nginx, or the platform's built-in
proxy in front to provide:

- **HTTPS** — a real certificate (Caddy/most platforms do this automatically).
- **A request-body cap** — e.g. nginx `client_max_body_size 4m;`. The app also
  rejects bodies over `MAX_EDI_CHARS` (2 MB) in `models.py`, but the proxy
  should stop the bytes before they reach Python.
- **A response timeout** — 30 s is plenty; a pathological input is already
  bounded by `MAX_ALLOWED_ITERATIONS`, but a timeout is a cheap backstop.
- **Rate limiting** — per-IP, e.g. 30 requests/minute. nginx `limit_req`, Caddy
  `rate_limit`, or Cloudflare in front. This is the one real gap for a public
  deployment: `POST /api/validate` and `/api/report` do real CPU work and have
  no throttle today.
- **Security headers** — `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, a strict `Content-Security-Policy` (the app
  loads only its own CSS/JS, no CDN, so `default-src 'self'` fits).

If you would rather the app carry its own rate limiting and headers instead of
leaning on the proxy, add `slowapi` + a small middleware — tracked as a possible
next step in `CLAUDE.md`.

### 3. Keep the privacy promise true

The UI tells every visitor "nothing you paste is stored, logged, or sent
anywhere." To keep that honest in production:

- Do **not** turn on uvicorn access logs that include request bodies, and do
  not let the proxy log POST bodies.
- No analytics scripts, no error tracker that captures request payloads (if you
  add Sentry etc., scrub the body).
- No persistence layer. If a feature ever needs to store a pasted interchange
  (e.g. the feedback idea in
  [#14](https://github.com/tidyedi/web-facing/issues/14)), that changes the
  promise and needs a deliberate decision + a UI change.

### 4. Operations

- **Health check** — the container has a `HEALTHCHECK` hitting `/healthz`; wire
  the platform's probe to the same path.
- **Updates** — this app pins x12-tidy to a commit in `uv.lock`. To pick up
  x12-tidy fixes: `uv lock --upgrade-package x12-tidy`, commit, rebuild, redeploy.
  The running commit is visible at `/healthz` and in the footer, so you can
  always tell what a deployment is serving.
- **Rollout** — the image is the release artifact; CI already builds it and
  smoke-tests `/healthz`. Tag images and keep the last known-good.

## Minimal path (Caddy + compose on a VPS)

```
# /etc/caddy/Caddyfile
tidy.tidyedi.com {
    encode gzip
    request_body {
        max_size 4MB
    }
    header {
        X-Content-Type-Options nosniff
        Referrer-Policy no-referrer
        Content-Security-Policy "default-src 'self'"
    }
    reverse_proxy 127.0.0.1:8000
}
```

```
docker compose up -d      # from this repo, on the VPS
systemctl reload caddy
```

That covers TLS, the body cap, headers, and a DNS record. For **rate limiting**,
pick one:

- Put Cloudflare (free tier) in front of the subdomain and add a rate-limit rule
  there — no server config, also gives you a CDN and basic bot filtering.
- Build Caddy with the [`caddy-ratelimit`](https://github.com/mholt/caddy-ratelimit)
  plugin and add a `rate_limit` block.
- Use nginx instead of Caddy — `limit_req` is built in.
- Add `slowapi` to the app itself (see `CLAUDE.md` "Not done").

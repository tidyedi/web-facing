# Deploying x12-tidy-web

Maintainer notes for standing up the one hosted instance (see
[#26](https://github.com/tidyedi/web-facing/issues/26)) — where it should live,
and what "functional for all" actually requires. This is not an invitation to
run separate public copies; the goal is a single canonical service.

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

For $0 options with step-by-step instructions, see [Deploying free](#deploying-free) below.

### 2. A reverse proxy in front (TLS + limits)

Never expose uvicorn directly. Put Caddy, nginx, or the platform's built-in
proxy in front to provide:

- **HTTPS** — a real certificate (Caddy/most platforms do this automatically).
- **A request-body cap** — e.g. nginx `client_max_body_size 4m;`. The app also
  rejects bodies over `MAX_EDI_CHARS` (2 MB) in `models.py`, but the proxy
  should stop the bytes before they reach Python.
- **A response timeout** — 30 s is plenty; a pathological input is already
  bounded by `MAX_ALLOWED_ITERATIONS`, but a timeout is a cheap backstop.
- **Rate limiting** — the app already limits `POST /api/validate` and
  `/api/report` to a shared **30 requests/minute per IP** (`slowapi`; set
  `X12_TIDY_WEB_RATE_LIMIT`, e.g. `"60/minute"`, or `"off"`). Add a proxy or
  Cloudflare rule on top if you want to throttle the whole site, not just the
  repair calls. On a host where you *can't* put a proxy in front (Hugging Face
  Spaces), the built-in limit is your only layer — keep it on.
- **Security headers** — `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, a strict `Content-Security-Policy` (the app
  loads only its own CSS/JS, no CDN, so `default-src 'self'` fits). These are
  not set by the app; add them at the proxy.

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

## Deploying free

Every option below costs $0 for this app's traffic. The trade is always one of:
sleeps when idle, needs a card on file for verification (never charged), or you
launch on the platform's URL instead of a custom domain.

| Platform | Card needed? | Trade-off |
| --- | --- | --- |
| **Hugging Face Spaces** (Docker) | No | Sleeps after ~48 h idle, wakes in seconds; custom domain needs the paid tier. `*.hf.space` URL. |
| **Google Cloud Run** | Yes (billing enabled, stays in free tier) | Scales to zero, ~1–3 s cold start; 2 M requests/mo free; custom domain + auto-HTTPS supported. |
| **Render** (free web service) | No | Spins down after 15 min idle → 30–60 s cold start. `*.onrender.com` URL. |
| **Oracle Cloud "Always Free" VM** | Yes (verification) | A real always-on VM; run `docker compose` + Caddy as in the VPS section below. No sleep. |

Rate limiting on the managed platforms (HF, Render): you can't put nginx/Caddy in
front, but the app's built-in per-IP limit on the repair endpoints (30/min,
`X12_TIDY_WEB_RATE_LIMIT`) covers you. On Cloud Run or a VPS you can also put
Cloudflare's free tier in front of a custom domain for whole-site limiting.

### Hugging Face Spaces (recommended for a no-cost launch)

1. **Create the Space** — <https://huggingface.co/new-space>, SDK **Docker**,
   blank template, visibility **Public**. Name it e.g. `x12-tidy-web`.
2. **Add the Space metadata** to `README.md` — a YAML block at the very top:

   ```yaml
   ---
   title: x12-tidy-web
   emoji: "\U0001F9F9"
   colorFrom: green
   colorTo: gray
   sdk: docker
   app_port: 8000
   pinned: false
   license: apache-2.0
   ---
   ```

   HF requires this; GitHub renders it as a small table above the README, which
   is the normal cost of the pattern. `app_port` matches the container's default
   (the CLI serves on `$PORT` if set, else 8000).
3. **Push this repo to the Space:**

   ```bash
   git remote add space https://huggingface.co/spaces/<user>/x12-tidy-web
   git push space main
   ```

   Authenticate with a write token from
   <https://huggingface.co/settings/tokens> (use it as the git password, or run
   `huggingface-cli login` first).
4. The Space builds the `Dockerfile` automatically — watch the **Logs** tab. The
   build fetches x12-tidy from GitHub (allowed) and takes a few minutes the
   first time.
5. Done: `https://<user>-x12-tidy-web.hf.space`.

If the container fails to start with a permission error, HF runs containers as
UID 1000 — change the `Dockerfile`'s `useradd --uid 10001 app` to `--uid 1000`
and rebuild. (The app writes nothing, so this usually is not needed.)

To keep the two copies in sync afterwards, push to both remotes (`git push
origin main && git push space main`) or add a GitHub Action that mirrors on
release.

### Google Cloud Run

1. Install the `gcloud` CLI, then `gcloud init` and pick/create a project with
   billing enabled (Cloud Run's free tier — 2 M requests, 360k GB-s, 180k
   vCPU-s per month — covers this app; you stay at $0, but a card must be on
   file).
2. From the repo root:

   ```bash
   gcloud run deploy x12-tidy-web \
     --source . \
     --region us-central1 \
     --allow-unauthenticated \
     --memory 512Mi --cpu 1 \
     --timeout 30 --concurrency 40 --max-instances 3
   ```

   `--source .` builds the `Dockerfile` with Cloud Build (it has GitHub access
   for the x12-tidy install) and enables the APIs it needs on first run.
3. Cloud Run sets `$PORT` (8080); the CLI honours it, so no image change is
   needed. The command prints the service URL (`https://x12-tidy-web-*.run.app`).
4. Custom domain later: `gcloud run domain-mappings create --service
   x12-tidy-web --domain tidy.tidyedi.com` (or map it through the console), then
   add the DNS records it shows. Put Cloudflare's free tier in front for rate
   limiting.

To redeploy after an update: re-run the same `gcloud run deploy` command.

### Render (free web service)

1. <https://dashboard.render.com> → **New → Web Service** → connect
   `tidyedi/web-facing`.
2. Runtime **Docker** (it finds the `Dockerfile`), instance type **Free**,
   region of your choice. No start command — the `Dockerfile` `CMD` is used and
   Render sets `$PORT`, which the CLI honours.
3. Deploy. URL is `https://<name>.onrender.com`. Auto-redeploys on every push to
   `main`.

The free instance spins down after 15 minutes idle and cold-starts (~30–60 s)
on the next request. No credit card.

## Running on several free hosts at once

The app is stateless — no database, no shared session state — so the same
container can run on any number of hosts simultaneously, each with its own URL.
Reasons to:

- **Availability** — one host sleeping, cold, or down, visitors use another.
- **Reachability** — different domains (`*.hf.space`, `*.onrender.com`,
  `*.run.app`) have different reputations with corporate/network filters; a
  visitor blocked from one may reach another.

Each rate limit (`slowapi`) counts per instance, which is fine — it is per-IP
either way. Nothing needs to be coordinated between instances.

**No-credit-card pair:** Hugging Face Spaces + Render (both above). Add Cloud Run
if you enable billing.

### Keeping them in sync

`render.yaml` (committed) lets Render pick up its own config; HF redeploys when
you push to the Space remote. To avoid deploying by hand three times, a GitHub
Action can fan a release out to all of them:

```yaml
# .github/workflows/deploy.yml  (sketch — fill in per-host secrets)
name: Deploy
on:
  release:
    types: [published]
jobs:
  huggingface:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: |
          git remote add space https://user:${{ secrets.HF_TOKEN }}@huggingface.co/spaces/<owner>/x12-tidy-web
          git push space HEAD:main --force
  # Render and Cloud Run redeploy from GitHub automatically once connected;
  # add explicit steps here only if you want the release to gate them.
```

### One URL in front of several

If you want a single address that fails over between instances, put a free
Cloudflare account in front of a custom domain (`tidy.tidyedi.com`) with a
load-balancing / failover rule pointing at the instance URLs. Otherwise you
publish the list of URLs (e.g. on the landing page) and let visitors pick.

## VPS path (Caddy + compose)

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

That covers TLS, the body cap, headers, and a DNS record. The app already
rate-limits the repair endpoints per IP; for **whole-site** limiting on top, add
Cloudflare's free tier in front, build Caddy with the
[`caddy-ratelimit`](https://github.com/mholt/caddy-ratelimit) plugin, or use
nginx (`limit_req` is built in).

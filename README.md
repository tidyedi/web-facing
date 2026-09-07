<h1>
  <img src="https://raw.githubusercontent.com/tidyedi/x12-tidy/main/docs/images/brand/tidyedi-mark.svg" alt="" width="48" height="48" align="left">
  &nbsp;x12-tidy-web
</h1>

[![CI](https://github.com/tidyedi/web-facing/actions/workflows/ci.yml/badge.svg)](https://github.com/tidyedi/web-facing/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

[![Repair malformed X12 EDI: a malformed file (email header before the ISA, lowercase tag, short elements, wrong group count) → iterative repair (locate the ISA, recover delimiters, pad to fixed width, rebuild the envelope) → a conformant copy plus a per-pass report of every finding. Private by design, no account, nothing to install.](docs/social-preview.png)](https://repair.tidyedi.com)

A small web front end for [**x12-tidy**](https://github.com/tidyedi/x12-tidy).
Paste a malformed ANSI X12 interchange into a form; get back a cleansed,
conformant copy plus a per-pass report of what changed. Take the corrected
string or leave it, and download the report as JSON, Markdown, HTML, text, or a
CSV of findings. Nothing you paste is stored, logged, or sent anywhere — the
repair runs in memory and is forgotten when the response is sent.

Part of [TidyEDI](https://github.com/tidyedi). x12-tidy does all of the EDI work
— this repo is just the iteration loop around it and the HTTP layer.

**Use it: <https://repair.tidyedi.com>** — a landing page with two ways in:

- **Repair your file** — paste your own interchange, take the corrected copy and
  a downloadable report.
- **See worked examples** — five broken samples already repaired: findings,
  corrected envelope, pass-by-pass diff. Plain pages, no account, nothing to
  enter — a quick look at what the tool does.

The worked examples are also served directly at
<https://tidyedi.github.io/web-facing/demo/>.

![The results view: verdict, corrected interchange, and envelope facts](docs/screenshot.png)

Want to help? See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## What it does

1. **Iterative repair.** It runs `x12_tidy.tidy()` on your input, feeds the
   cleansed payload back in, and repeats until the result comes back clean, stops
   changing, or can't be recovered at all. Every pass is recorded.
2. **A readable report.** Pass 1 shows the gross structural repairs; later passes
   show only what survives them. Each finding carries x12-tidy's severity, code,
   plain-English message, and byte offset into your original text.
3. **Your choice.** The corrected string is offered, never forced. Copy it, or
   don't.
4. **Download.** Export the whole run as JSON, Markdown, HTML, plain text, or a
   CSV of findings.

## Run it locally

For development, or to check a change against the real app:

```bash
uv sync                       # installs x12-tidy from its git repo
uv run x12-tidy-web serve     # http://127.0.0.1:8000
```

Options: `x12-tidy-web serve --host 0.0.0.0 --port 8080 --reload`. The server
honours `$PORT` when set.

Environment:

| Variable | Effect |
| --- | --- |
| `PORT` | Bind port when `--port` isn't given (Cloud Run, Render, Fly set it). |
| `X12_TIDY_WEB_RATE_LIMIT` | Per-IP limit on the repair endpoints (`"30/minute"` default; `"off"` to disable). |
| `X12_TIDY_WEB_FEEDBACK_EMAIL` | Address for the "report a wrong result" `mailto:` link. Unset → link hidden. |

### Docker

```bash
docker compose up --build     # http://127.0.0.1:8000
```

The container is the release artifact — `python:3.12-slim`, non-root,
read-only, a `HEALTHCHECK` on `/healthz`, and it honours `$PORT`. Any host that
runs a container runs this. Deployment and operational notes are kept in a
separate private repo.

### Static demo

For a zero-install look, or an environment that can't reach the live app:

```bash
uv run x12-tidy-web demo            # writes ./x12-tidy-web-demo/
```

One self-contained HTML file per sample — CSS and favicon inlined, every link
relative or external, no server. A committed copy is in
[`docs/demo/`](docs/demo/), served rendered at
**<https://repair.tidyedi.com/demo/>** (and its raw GitHub Pages address,
<https://tidyedi.github.io/web-facing/demo/>).

## The HTTP API

The form is a thin client over a JSON API you can call directly.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| `POST` | `/api/validate` | `{"edi": "...", "max_iterations": 5}` | the full repair run as JSON |
| `POST` | `/api/report` | `{"edi": "...", "max_iterations": 5, "format": "markdown"}` | the report as a file download |
| `GET`  | `/api/formats` | — | the available report formats |
| `GET`  | `/api/codes` | — | every diagnostic code the installed x12-tidy can emit |
| `GET`  | `/codes` | — | human-readable reference page for the above |
| `GET`  | `/healthz` | — | `{"status": "ok", "x12_tidy_web": "…", "x12_tidy": "…", "x12_tidy_commit": "…"}` |

`/healthz`, `/api/codes`, the footer, `x12-tidy-web --version`, and every
downloaded report (bar CSV) carry the git commit x12-tidy was installed from, so
a screenshot or a saved report pins the exact build that produced a result.

```bash
curl -s localhost:8000/api/validate \
  -H 'content-type: application/json' \
  -d '{"edi": "ISA*00*...~IEA*1*000000001~"}' | jq .converged
```

### The repair-run shape

```jsonc
{
  "schema": "x12-tidy-web/repair-run/1",
  "converged": true,
  "recovered": true,          // an ISA line was found
  "clean": false,             // findings remain after the last pass
  "changed": true,            // corrected text differs from input
  "stop_reason": "stable",    // clean | stable | unrecoverable | max-iterations
  "original_text": "...",
  "final_text": "ISA*00*          *00* ...",
  "residual_severity_counts": { "fatal": 1, "error": 0, "warning": 0 },
  "final_facts": { "sender_id": "ACME", "functional_group_count": 1, ... },
  "iterations": [
    {
      "index": 1,
      "changed": true,
      "was_clean": false,
      "severity_counts": { "fatal": 0, "error": 2, "warning": 1 },
      "diagnostics": [
        { "severity": "error", "code": "isa.element-width",
          "message": "ISA06 is 4 byte(s); padded ...", "offset": 42, "...": "..." }
      ],
      "input_text": "...", "output_text": "..."
    }
  ]
}
```

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run mypy src
```

x12-tidy is always imported from its git repo — never cloned, vendored, or
path-linked into this one (`tests/test_dependency_provenance.py` enforces it).
To test against unreleased x12-tidy work, push it to a branch and point the
`x12-tidy @ git+…@<branch>` ref in `pyproject.toml` at it, then `uv lock`.

### Layout

```
src/x12_tidy_web/
  engine.py      the iterative-repair loop (repair() -> RepairRun)
  diagnostics.py x12-tidy's severity-free Diagnostic -> a display row
  reporting.py   render a RepairRun as JSON / Markdown / HTML / text / CSV
  provenance.py  which x12-tidy build is installed (footer, /healthz, links)
  samples.py     the five broken samples the form and demo pages share
  demo.py        build the static demo bundle
  models.py      Pydantic request/response schemas
  app.py         the FastAPI app: form page + JSON API + downloads
  cli.py         `x12-tidy-web serve | repair | demo`
  templates/     server-rendered shells (form, code reference, static demo)
  static/        styles.css, app.js, favicon.svg — no build step
```

## The one rule this repo follows

Everything about X12 — locating the ISA line, recovering delimiters,
reconstructing the envelope, auditing control numbers — lives in
[x12-tidy](https://github.com/tidyedi/x12-tidy) and is **imported**, never copied
here. This repo adds only the loop, the renderers, and the web layer. If a
finding looks wrong, it's an x12-tidy question.

## License

[Apache License 2.0](LICENSE) — © 2026 Michael Schertz. See [`NOTICE`](NOTICE).

"TidyEDI" and the TidyEDI logo are trademarks of Michael Schertz; the license
covers the code, not the name or the mark.

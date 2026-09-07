# CLAUDE.md — x12-tidy-web

Working notes for anyone (human or agent) touching this repo.

## What this is

A web front end for [x12-tidy](https://github.com/tidyedi/x12-tidy). A visitor
pastes a malformed X12 interchange; the server repairs it *iteratively* and
returns the corrected string plus a per-pass report the visitor can download.

## The one rule

**All X12 knowledge lives in x12-tidy and is imported, never copied here.**
Locating the ISA line, recovering delimiters, reconstructing the envelope,
auditing control numbers — none of that logic belongs in this repo. If a finding
is wrong or missing, fix it in x12-tidy and bump the pin.

x12-tidy is a dependency pulled straight from its git repo (no PyPI release
yet), pinned in `pyproject.toml` (`x12-tidy @ git+https://…@main`) and locked in
`uv.lock`. **Never clone, vendor, or path-link x12-tidy into this repo** — not
even a commented-out `[tool.uv.sources]` entry. It is imported like any other
third-party package so that a change in x12-tidy reaches this repo only when you
deliberately bump the ref and re-run `uv lock`. To test against unreleased
x12-tidy work, push that work to a branch and point the ref at it.
`tests/test_dependency_provenance.py` fails loudly if this is ever violated.

### Which repo owns a bug?

Reproduce against x12-tidy alone, no web layer:

```
uv run x12-tidy path/to/broken.edi
uv run python -c "from x12_tidy import tidy; print(tidy(open('broken.edi','rb').read()))"
```

- Corrected string / a finding / severity / byte offset is wrong → **x12-tidy**.
  Fix there, then `uv lock --upgrade-package x12-tidy` here.
- One pass is right but the loop, the report, the JSON/CSV, the API, the form or
  the CLI misbehaves → **here**.

Every result is stamped with the x12-tidy git commit (footer, `/healthz`,
`/api/codes`, `--version`, downloaded reports) — `provenance.py`. A bug report
that includes any of those pins the exact build to reproduce against.

## Architecture

```
src/x12_tidy_web/
  engine.py      repair() -> RepairRun. The loop: run x12_tidy.tidy(), feed the
                 cleansed payload back in, stop on clean | stable | unrecoverable
                 | max-iterations. Pure — no I/O.
  diagnostics.py x12-tidy's severity-free Diagnostic -> DiagnosticView (severity
                 resolved, registry title/explanation attached).
  reporting.py   render_report(run, fmt) -> Report(bytes, media_type, filename).
                 Formats: json (lossless), markdown, html, text, csv. Every
                 format except csv credits the x12-tidy build that produced it.
  provenance.py  x12_tidy_version / _commit / _release / _source_url: which
                 x12-tidy is installed, read from its direct_url.json. Surfaced
                 in the footer, /healthz, /api/codes, `--version`, reports, and
                 the "diagnostic code registry" link, so a screenshot or saved
                 report pins the exact build.
  samples.py     SAMPLES: the three broken interchanges the form's "Load a
                 random sample" and the demo pages both use. Source of truth;
                 `python -m x12_tidy_web.samples` regenerates samples/*.edi.
  demo.py        build_demo(out_dir): the static demo bundle (x12-tidy-web
                 demo) — one self-contained HTML file per sample plus a static
                 /codes and index. Inlines CSS + favicon; every link relative
                 or absolute-external.
  models.py      Pydantic request schemas. The response is RepairRun.as_dict()
                 verbatim, so the wire shape has exactly one definition (engine).
  app.py         FastAPI: GET / (form), GET /codes (code reference page),
                 POST /api/validate, POST /api/report, GET /api/formats,
                 GET /api/codes, GET /healthz.
  cli.py         `x12-tidy-web serve`, `x12-tidy-web repair FILE`, and
                 `x12-tidy-web demo [OUT_DIR]`.
  templates/     server-rendered shells: index.html (the form), codes.html
                 (the /codes reference; also static-mode for the demo bundle),
                 demo.html + demo_index.html (the static demo), _nav.html (the
                 link row shared by the top navbar and footer of every page).
  static/        styles.css, app.js, favicon.svg. Vanilla JS, no build, no CDN.
```

GitHub Pages (source: `main` `/docs`, `docs/.nojekyll`, `docs/CNAME` =
`repair.tidyedi.com`) serves **the published entry point**:
- `docs/index.html` at <https://repair.tidyedi.com> — the landing page. Two
  cards: **"Repair your file"** (→ the Render URL) and **"See worked
  examples"** (→ `demo/`).
  This page is deliberately on GitHub Pages, not the app's host: a visitor whose
  network blocks Render can't be helped by anything *on* Render (block pages are
  intercepted, not detectable; the free instance's ~50 s cold start defeats
  timeouts too), so the entry point must be a plain page on a rarely-filtered
  host that just shows both options. Don't "improve" this with auto-detection.
- `docs/demo/` — the generated bundle, also at
  <https://repair.tidyedi.com/demo/>. Regenerate with
  `uv run x12-tidy-web demo docs/demo` after changing samples, templates, or the
  x12-tidy pin, then commit. Pages redeploys on push. (`build_demo` writes named
  files, doesn't wipe the dir, so `docs/CNAME` is safe.)

The live app itself is on Render at `x12-tidy-web.onrender.com` (free tier,
Docker, auto-deploys on push; `render.yaml`). See `docs/DEPLOYMENT.md`.

If the app's URL changes (moves host, gets its own `*.tidyedi.com`), update all
of: the `<!-- LIVE-APP-CARD -->` href in `docs/index.html`, the repo Website
field (`gh repo edit … --homepage`), `demo.py`'s `static_nav["home_href"]`,
`_nav.html`'s `demo_href` default, `README.md`, and `docs/DEPLOYMENT.md`.

### Why iterate?

One `tidy()` call already reconstructs the envelope. Iterating keeps the
*report* honest: pass 1 shows the gross structural repairs; pass 2 (on the
now-canonical payload) shows only what survives them — typically QA/QC trust
signals like a control-count mismatch that x12-tidy reports but cannot fix. When
a pass changes no bytes, further passes would be identical, so the loop stops
("stable"). Most inputs converge in 1–2 passes.

### Bytes vs text

X12 is bytes; the web form gives text. The boundary codec is **latin-1**
everywhere (`engine.TEXT_CODEC`) — a total, round-tripping map for bytes 0–255,
which x12-tidy's own docs recommend for handling payloads as text.

## Conventions

- Type hints on everything; `uv run mypy src` is clean and `strict`.
- `uv` for everything. `uv.lock` is committed.
- src/ layout. Templates and static files are package data (see the
  `force-include` in `pyproject.toml`) so they ship in the wheel / Docker image.
- Tests: `uv run pytest`. `tests/conftest.py` holds the clean/dirty/not-EDI
  fixtures and a `TestClient`.

## Checks before a PR

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
```

CI additionally builds the Docker image and hits `/healthz` in the container.

## Not done / possible next steps

- Per-IP rate limiting on the two repair endpoints is built in (`slowapi`,
  30/min shared, `X12_TIDY_WEB_RATE_LIMIT` to tune or `off` to disable). No
  request-size middleware beyond `MAX_EDI_CHARS` in `models.py`; put a body cap
  at the proxy for a public deploy — see `docs/DEPLOYMENT.md`.
- No persistence by design — nothing pasted is stored or logged. Keep it that
  way unless there's a deliberate decision otherwise.
- Open issues on the remote (tidyedi/web-facing): #10 (server-sent email —
  declined for now, privacy), #15–#19 (marketing backlog, "later:"), #26
  (deployment — `docs/DEPLOYMENT.md` is the answer, waiting on a platform pick).
- The app is stateless, so it can run on several free hosts at once for
  availability + reachability behind network filters. `render.yaml` is a Render
  blueprint; `docs/DEPLOYMENT.md` has the multi-host section (HF + Render +
  Cloud Run, a fan-out Action sketch, and the single-URL failover option).
- Feedback on a diagnostic code goes to x12-tidy's Q&A discussions, not here —
  the per-code "Discuss" links on `/codes` build a pre-filled URL
  (`diagnostics._discuss_url`). "Report a wrong result" is an opt-in `mailto:`
  (`X12_TIDY_WEB_FEEDBACK_EMAIL`); the interchange is never auto-attached.
- The "read it segment by segment" view (#7) is JS-only in `app.js`
  (`explodeSegments`): it splits the corrected bytes on the terminator x12-tidy
  fixed at ISA byte 105 and re-lays them out. Not ported to the demo pages.

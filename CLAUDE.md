# CLAUDE.md — x12-tidy-web

Working notes for anyone (human or agent) touching this repo.

## What this is

A web front end for [x12-tidy](https://github.com/tidyedi/x12-tidy). A visitor
pastes a malformed X12 interchange; the server repairs it *iteratively* and
returns the corrected string plus a per-pass report the visitor can download.

## The one rule

This is a rule for **the maintainers, when working in this repo**. x12-tidy
itself changes the normal way — through its own repo's review-and-release
process. What is forbidden is changing x12-tidy *from here*.

**All X12 knowledge lives in x12-tidy and is imported, never copied or edited
here.** Locating the ISA line, recovering delimiters, reconstructing the
envelope, auditing control numbers — none of that logic belongs in this repo.
When you are in `web-facing` and find an x12-tidy finding that is wrong or
missing, the fix does **not** go here: make it in the x12-tidy repo, land it
there through its own process, then bump the pin in this one.

Why the rule exists: if x12-tidy logic were vendored, path-linked, or patched
inside `web-facing`, that change would have no history in x12-tidy, would not
carry back to it, and every other consumer would silently diverge from what this
repo runs. Importing it as a plain pinned dependency keeps x12-tidy the single
place its behaviour is defined and reviewed.

Mechanically: x12-tidy is pulled straight from its git repo (no PyPI release
yet), pinned in `pyproject.toml` (`x12-tidy @ git+https://…@main`) and locked in
`uv.lock`, so an upstream change reaches this repo only when a maintainer
deliberately bumps the ref and re-runs `uv lock`. **Never clone, vendor, or
path-link x12-tidy into this repo** — not even a commented-out
`[tool.uv.sources]` entry. To try this repo against unreleased x12-tidy work,
push that work to an x12-tidy branch and point the ref at it — still an import,
never a local edit. `tests/test_dependency_provenance.py` fails loudly if this
is ever violated.

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
  cards: **"Repair your file"** (→ the live app) and **"See worked examples"**
  (→ `demo/`). It lives on GitHub Pages, separate from the app, so it stays
  fast and available regardless of the app's state and gives the visitor a
  clear choice between the two. Keep it a plain static page.
- `docs/demo/` — the generated bundle, also at
  <https://repair.tidyedi.com/demo/>. Regenerate with
  `uv run x12-tidy-web demo docs/demo` after changing samples, templates, or the
  x12-tidy pin, then commit. Pages redeploys on push. (`build_demo` writes named
  files, doesn't wipe the dir, so `docs/CNAME` is safe.)

The live app is on Render (Docker, auto-deploys on push; `render.yaml`).
Deployment, hosting, and operational detail live in a **private** repo, not
here — ask a maintainer.

If the app's URL changes (moves host, gets its own `*.tidyedi.com`), update all
of: the `<!-- LIVE-APP-CARD -->` href in `docs/index.html`, the repo Website
field (`gh repo edit … --homepage`), `demo.py`'s `static_nav["home_href"]`,
`_nav.html`'s `demo_href` default, and `README.md`.

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
  request-size middleware beyond `MAX_EDI_CHARS` in `models.py`.
- No persistence by design — nothing pasted is stored or logged. Keep it that
  way unless there's a deliberate decision otherwise.
- The app is stateless (no DB, no shared state), so it can run on more than one
  host. Deployment specifics are in the private ops repo.
- Feedback paths (no dedicated form — a `feedback.html` form was built and
  rejected; the main funnel is the Medium/LinkedIn article comment sections):
  - **"Feedback"** nav link + the post-repair prompt → a new **Ideas**
    discussion on `tidyedi/web-facing`
    (`/discussions/new?category=ideas` — hard-coded in `_nav.html`,
    `templates/index.html`, `docs/index.html`). Needs a GitHub account.
  - Per-code **"Discuss"** on `/codes` → a pre-filled x12-tidy Q&A discussion
    (`diagnostics._discuss_url`) — that's where diagnostic changes are made.
  - **"report a wrong result"** — opt-in `mailto:` on the results panel
    (`X12_TIDY_WEB_FEEDBACK_EMAIL`, unset → hidden; the interchange is never
    auto-attached). The one no-account path.
- The "read it segment by segment" view (#7) is JS-only in `app.js`
  (`explodeSegments`): it splits the corrected bytes on the terminator x12-tidy
  fixed at ISA byte 105 and re-lays them out. Not ported to the demo pages.

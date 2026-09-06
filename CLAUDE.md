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
  provenance.py  x12_tidy_version / _commit / _release: which x12-tidy is
                 installed, read from its direct_url.json. Surfaced in the
                 footer, /healthz, /api/codes, `--version`, and reports so a
                 screenshot or a saved report pins the exact build.
  models.py      Pydantic request schemas. The response is RepairRun.as_dict()
                 verbatim, so the wire shape has exactly one definition (engine).
  app.py         FastAPI: GET / (form), GET /codes (code reference page),
                 POST /api/validate, POST /api/report, GET /api/formats,
                 GET /api/codes, GET /healthz.
  cli.py         `x12-tidy-web serve` and `x12-tidy-web repair FILE`.
  templates/     server-rendered shells: index.html (the form) and
                 codes.html (the /codes reference, from diagnostics.code_reference).
  static/        styles.css + app.js. Vanilla JS, no build step, no CDN.
```

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

- No rate limiting or request-size middleware beyond the `MAX_EDI_CHARS` check
  in `models.py`. Add a reverse proxy or slowapi if deployed publicly — see
  `docs/DEPLOYMENT.md`.
- No persistence by design — nothing pasted is stored or logged. Keep it that
  way unless there's a deliberate decision otherwise.
- Open UI issues on the remote (tidyedi/web-facing): #5/#6/#9/#12 (visual
  polish), #7 (a pretty-printed segment view — decide x12-tidy vs. local),
  #10 (feature brainstorm). #1–#4, #8, #11 landed together as the
  "explanation layer" pass.

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
`uv.lock`. For a fast local loop against a sibling checkout, uncomment the
`[tool.uv.sources]` line and `uv sync`.

## Architecture

```
src/x12_tidy_web/
  engine.py      repair() -> RepairRun. The loop: run x12_tidy.tidy(), feed the
                 cleansed payload back in, stop on clean | stable | unrecoverable
                 | max-iterations. Pure — no I/O.
  diagnostics.py x12-tidy's severity-free Diagnostic -> DiagnosticView (severity
                 resolved, registry title/explanation attached).
  reporting.py   render_report(run, fmt) -> Report(bytes, media_type, filename).
                 Formats: json (lossless), markdown, html, text, csv.
  models.py      Pydantic request schemas. The response is RepairRun.as_dict()
                 verbatim, so the wire shape has exactly one definition (engine).
  app.py         FastAPI: GET / (form), POST /api/validate, POST /api/report,
                 GET /api/formats, GET /api/codes, GET /healthz.
  cli.py         `x12-tidy-web serve` and `x12-tidy-web repair FILE`.
  templates/     one server-rendered shell (index.html).
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
  in `models.py`. Add a reverse proxy or slowapi if deployed publicly.
- `/api/codes` powers a reference page that does not exist yet in the UI.
- No persistence by design — nothing pasted is stored or logged. Keep it that
  way unless there's a deliberate decision otherwise.

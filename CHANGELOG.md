# Changelog

## v0.1.0 — 2026-09-06

First tagged release. A stateless web front end for
[x12-tidy](https://github.com/tidyedi/x12-tidy): paste a malformed ANSI X12
interchange, get an iteratively-repaired copy and a per-pass report.

### The app

- **Iterative repair** (`engine.repair`) — runs `x12_tidy.tidy()` to a fixed
  point, one `Iteration` per pass, stopping on clean / stable / unrecoverable /
  max-iterations.
- **The form** — paste or upload an interchange, or pick from five broken
  samples; get a verdict, the corrected interchange, the envelope facts, and
  every pass's findings. Filter a pass's findings by severity. Read the
  corrected bytes laid out segment-by-segment. Download the run as JSON,
  Markdown, HTML, text, or CSV.
- **Verdicts** are colour-coded: green for clean, amber for repaired-with-
  residual-findings, red for unrecoverable or not-repairable.
- **`/codes`** — a reference for every diagnostic code the installed x12-tidy
  can emit, grouped by area, filterable by severity, each row linking to a
  pre-filled discussion on x12-tidy.
- **JSON API** — `POST /api/validate`, `POST /api/report`, `GET /api/formats`,
  `GET /api/codes`, `GET /healthz`.
- **CLI** — `x12-tidy-web serve | repair FILE | demo [OUT_DIR]`.

### Provenance and the one rule

- All X12 knowledge lives in x12-tidy and is imported, never copied.
  `tests/test_dependency_provenance.py` fails if that is ever violated.
- Every result is stamped with the exact x12-tidy git commit — footer,
  `/healthz`, `/api/codes`, `--version`, and downloaded reports.

### Operations

- Per-IP rate limiting on the two repair endpoints (`slowapi`;
  `X12_TIDY_WEB_RATE_LIMIT`).
- `serve` honours `$PORT`; the Docker image runs read-only, non-root.
- Opt-in "report a wrong result" `mailto:` (`X12_TIDY_WEB_FEEDBACK_EMAIL`).
- Static demo bundle in `docs/demo/`, published at
  <https://tidyedi.github.io/web-facing/demo/>; landing page at
  <https://tidyedi.github.io/web-facing/>.
- Deployment guide (Hugging Face Spaces, Cloud Run, VPS) in
  `docs/DEPLOYMENT.md`.

### Not yet done

Hosting the canonical instance, an update mailing list, and a few
marketing/links items — see the open issues.

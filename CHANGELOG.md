# Changelog

## Unreleased

Changes on `main` since the v0.1.0 tag, not yet cut as a new version.

### Dependency

- Bumped the x12-tidy pin (`04bffa4` → `3ce03cf`). A CR/LF inside an ISA
  element is now **removed** rather than replaced with a space, so a header
  wrapped mid-value (`RECEIV<CRLF>ER`) is stitched back to `RECEIVER` instead of
  coming out as `RECEIV··ER`. The `isa.element-embedded-newline` message changed
  to "line break removed". Identified here, fixed upstream.

### Deployed

- **The canonical instance is live.** Landing page at
  <https://repair.tidyedi.com> (GitHub Pages, `main` `/docs`); the app on
  Render (Docker, `render.yaml`, Starter plan — always-on). Worked examples at
  <https://repair.tidyedi.com/demo/>. Deployment and ops detail moved to a
  private repo.
- Static assets are linked root-relative and `serve` trusts the platform's
  `X-Forwarded-Proto`, so the app renders correctly behind Render's
  TLS-terminating proxy (previously served `http://` asset URLs that the
  browser blocked as mixed content). This also makes the per-IP rate limit
  key on the real client IP.

### Changed

- **The verdict is decided in one place** (`RepairRun.verdict`) and rendered by
  the app, the report, and the demo alike. Any residual **fatal** finding now
  reads as "Cannot be repaired", and the payload is labelled a *partially
  repaired interchange — not conformant* with a caveat, never a "corrected
  interchange".
- The "Repair passes" section and every report format now explain the pass
  model (pass 1 repairs your input; later passes run on the prior output).
- Reports say "Why it stopped: <plain sentence>" instead of the internal
  `stop_reason` key.
- `CLAUDE.md`'s "one rule" reworded as maintainer-facing guidance about the
  x12-tidy import boundary.
- **"Feedback" (nav, footer, landing page) is now an email link**
  (`repair-feedback@tidyedi.com`) when a feedback address is configured — the
  no-account path — falling back to a GitHub discussion otherwise. The
  post-repair prompt is a clearer callout and pre-fills the run's verdict,
  version, and stop reason into the message.

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
- Static demo bundle in `docs/demo/`, published on GitHub Pages.
- Deployment guide in `docs/DEPLOYMENT.md` (later moved to a private ops repo;
  see the Unreleased section).

### Not yet done

An update mailing list and a few marketing/links items — see the open issues.

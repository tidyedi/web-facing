# How you can help

x12-tidy-web is a thin web layer over [x12-tidy][x12t]. Almost everything about
X12 — locating the ISA line, recovering delimiters, rebuilding the envelope,
auditing control numbers — lives in x12-tidy and is *imported* here, never
copied. That shapes where different kinds of help go.

## Try it and report what's wrong

The most useful thing: run a real (sanitised) interchange through it and tell us
what looked off.

- **The repaired output or a finding is wrong** → that's an **x12-tidy** issue,
  because that's where the logic is. From a result, use the **"report a wrong
  result"** link (if the deployment enabled it) or open an issue on
  [x12-tidy][x12t]. Every result carries the exact x12-tidy commit (footer,
  `/healthz`, downloaded reports), so include that.
- **The loop, the report, the UI, the API, or the CLI misbehaves** → open an
  issue *here*: <https://github.com/tidyedi/x12-tidy-web/issues>.
- **A diagnostic code's severity, wording, or coverage seems wrong** → each row
  on [`/codes`](https://tidyedi.github.io/x12-tidy-web/demo/codes.html) has a
  **Discuss** link that opens a pre-filled thread in
  [x12-tidy's Q&A discussions][disc].

To tell which side a bug is on, reproduce against x12-tidy alone:

```bash
uv run x12-tidy path/to/broken.edi
```

If that output is already wrong, it's x12-tidy. If it's right but this app shows
something different, it's here.

## Add or improve a sample

The five broken samples live in one place:
[`src/x12_tidy_web/samples.py`](src/x12_tidy_web/samples.py). A good sample has a
distinct repair story (a defect the others don't show) and a one-line blurb.
After editing, regenerate the derived files:

```bash
uv run python -m x12_tidy_web.samples        # rewrites samples/*.edi
uv run x12-tidy-web demo docs/demo            # rebuilds the static demo
```

## Code changes

```bash
uv sync --extra dev
uv run ruff check .
uv run mypy src
uv run pytest -q
```

All three must pass. CI additionally builds the Docker image and hits
`/healthz`. Conventions:

- Type hints on everything; `mypy src` is `strict` and clean.
- No X12 knowledge in this repo. If a fix belongs in x12-tidy, make it there and
  bump the pin (`uv lock --upgrade-package x12-tidy`).
- No persistence, no analytics, no request-body logging — the privacy promise in
  the UI has to stay true.
- Vanilla JS, no build step, no CDN.

See [`CLAUDE.md`](CLAUDE.md) for the architecture and the reasoning behind the
iteration loop.

[x12t]: https://github.com/tidyedi/x12-tidy
[disc]: https://github.com/tidyedi/x12-tidy/discussions/categories/q-a

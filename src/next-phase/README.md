# `src/next-phase/` — groundwork, not shipped

Exploratory code for the **planned next phase**: an EDI *translation* product
(read an interchange, resolve which implementation convention governs it, map
its segments). That is a different thing from what this repo ships today — a
stateless X12 *repair* utility.

**Nothing here is part of the `x12-tidy-web` package.** The wheel builds only
`src/x12_tidy_web` (`pyproject.toml` → `[tool.hatch.build.targets.wheel]
packages`), so this directory never reaches the app, the Docker image, or PyPI.
It is checked in so the exploration has a home and a history, kept physically
separate so it can't leak into the product by accident.

It *imports* the installed `x12_tidy_web` (for the repair engine and the sample
corpus) the same way any consumer would — it does not reach into internals.

The directory name has a hyphen on purpose: it is not an importable Python
package, only a folder of scripts you run directly.

## Contents

| File | What it does |
|---|---|
| `identify_conventions.py` | Issue #79. For each bundled sample: cleanse it, name the X12 standard / implementation convention it follows, and inventory its segments. Writes `sample_conventions.md` and `sample_conventions.json`. |

## Run

```bash
uv run python src/next-phase/identify_conventions.py
```

Outputs land next to the script.

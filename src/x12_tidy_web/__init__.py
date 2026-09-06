# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""x12-tidy-web: a web front end for the x12-tidy validator/repairer.

A visitor pastes a (possibly malformed) ANSI X12 interchange into a form. The
server runs :func:`x12_tidy.tidy` on it, feeds the cleansed payload back in, and
repeats until the result stops changing or comes back clean -- an *iterative*
repair. Every pass is recorded, so the visitor sees not just the final corrected
string but what each round fixed, and can download the whole run as a report in
the format they choose.

The only external dependency that matters is :mod:`x12_tidy`. Everything x12-tidy
knows about X12 lives there; this package adds the loop, the report renderers,
and the HTTP layer.

Layout::

    engine       the iterative-repair loop (:func:`repair` -> :class:`RepairRun`)
    diagnostics  turn x12-tidy's severity-free ``Diagnostic`` into a display row
    reporting    render a ``RepairRun`` as JSON / Markdown / HTML / text / CSV
    models       Pydantic request/response schemas for the JSON API
    app          the FastAPI application (form page + JSON API + downloads)
    cli          ``x12-tidy-web serve`` -- run the app with uvicorn
"""

from x12_tidy_web.engine import (
    DEFAULT_MAX_ITERATIONS,
    EnvelopeFactsView,
    Iteration,
    RepairRun,
    repair,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "EnvelopeFactsView",
    "Iteration",
    "RepairRun",
    "repair",
]

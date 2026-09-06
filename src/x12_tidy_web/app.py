# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The FastAPI application.

Routes:

* ``GET  /``            -- the single-page form (server-rendered shell).
* ``POST /api/validate``-- run the iterative repair, return it as JSON.
* ``POST /api/report``  -- same run, streamed back as a downloadable file.
* ``GET  /codes``       -- human reference page for every diagnostic code.
* ``GET  /api/formats`` -- the report formats on offer.
* ``GET  /api/codes``   -- every diagnostic code the installed x12-tidy emits.
* ``GET  /healthz``     -- liveness probe; also reports the x12-tidy git commit.

All EDI knowledge is in :mod:`x12_tidy`; the loop is in
:mod:`x12_tidy_web.engine`; this module is just wiring.

The two repair endpoints (``/api/validate`` and ``/api/report``) do real,
synchronous CPU work and have no auth, so they carry a per-IP rate limit
(:mod:`slowapi`). This matters on public deploys where nothing else fronts the
app -- Hugging Face Spaces, say, where you cannot put a proxy in front. Set
``X12_TIDY_WEB_RATE_LIMIT`` (a `limits`_ string like ``"30/minute"``, the
default) to change it, or ``"off"`` to disable it (e.g. when a proxy already
rate-limits). GET routes and static files are not limited here -- a flood of
those is cheap and better handled at the infrastructure layer.

.. _limits: https://limits.readthedocs.io/en/stable/quickstart.html#rate-limit-string-notation
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from x12_tidy_web import __version__
from x12_tidy_web.diagnostics import AREA_LABELS, code_catalog, code_reference
from x12_tidy_web.engine import DEFAULT_MAX_ITERATIONS, MAX_ALLOWED_ITERATIONS, repair
from x12_tidy_web.models import ReportRequest, ValidateRequest
from x12_tidy_web.provenance import (
    x12_tidy_commit,
    x12_tidy_release,
    x12_tidy_source_url,
    x12_tidy_version,
)
from x12_tidy_web.reporting import available_formats, render_report
from x12_tidy_web.samples import SAMPLES

_HERE = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))

#: The diagnostic code registry inside x12-tidy — the single source of truth for
#: every finding's code, title, severity, and explanation (issues #4, #22).
_REGISTRY_PATH = "src/x12_tidy/diagnostics/codes.py"

_RATE_LIMIT_DEFAULT = "30/minute"
_RATE_LIMIT_DISABLED = {"", "0", "off", "none", "disabled", "false"}


def _feedback_email() -> str:
    """Address for the "report a wrong result" link, or "" to hide it.

    Set ``X12_TIDY_WEB_FEEDBACK_EMAIL`` on the deployment. The link is a plain
    ``mailto:`` — the interchange is never attached automatically, the visitor
    decides what to paste.
    """
    return os.environ.get("X12_TIDY_WEB_FEEDBACK_EMAIL", "").strip()


def _rate_limit() -> tuple[str, bool]:
    """``(limit string, enabled)`` from ``X12_TIDY_WEB_RATE_LIMIT``.

    The limit applies per client IP to the two repair endpoints. ``"off"`` (or
    ``0``/``none``/…) disables it — do that only when something else in front of
    the app already rate-limits. Read here (not at import) so it is testable.
    """
    raw = os.environ.get("X12_TIDY_WEB_RATE_LIMIT", _RATE_LIMIT_DEFAULT).strip()
    if raw.lower() in _RATE_LIMIT_DISABLED:
        return "1000000/minute", False  # decorator still needs a valid string
    return raw, True


def create_app() -> FastAPI:
    app = FastAPI(
        title="x12-tidy-web",
        version=__version__,
        description="Web front end for x12-tidy: iterative X12 EDI repair with a downloadable report.",
    )

    rate_limit, rate_limit_enabled = _rate_limit()
    limiter = Limiter(
        key_func=get_remote_address,
        enabled=rate_limit_enabled,
        headers_enabled=True,  # emit X-RateLimit-* and Retry-After
        retry_after="delta-seconds",
    )
    app.state.limiter = limiter
    # one shared per-IP budget across both repair endpoints, not one each
    repair_limit = limiter.shared_limit(rate_limit, scope="repair")
    # slowapi's handler is typed (Request, RateLimitExceeded) -> Response; Starlette
    # wants (Request, Exception). The narrower signature is safe here.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "app_version": __version__,
                "x12_tidy_release": x12_tidy_release(),
                "registry_url": x12_tidy_source_url(_REGISTRY_PATH),
                "default_max_iterations": DEFAULT_MAX_ITERATIONS,
                "max_allowed_iterations": MAX_ALLOWED_ITERATIONS,
                "formats": available_formats(),
                "samples": [
                    {"slug": s.slug, "title": s.title, "blurb": s.blurb, "edi": s.edi}
                    for s in SAMPLES
                ],
                "config": {
                    "feedbackEmail": _feedback_email(),
                    "x12TidyRelease": x12_tidy_release(),
                },
                "current": "repair",
            },
        )

    @app.get("/codes", response_class=HTMLResponse)
    def codes_page(request: Request) -> HTMLResponse:
        catalog = code_catalog()
        return _TEMPLATES.TemplateResponse(
            request,
            "codes.html",
            {
                "app_version": __version__,
                "x12_tidy_release": x12_tidy_release(),
                "registry_url": x12_tidy_source_url(_REGISTRY_PATH),
                "codes": catalog,
                "by_area": code_reference(),
                "area_labels": AREA_LABELS,
                "fatal_count": sum(c["severity"] == "fatal" for c in catalog),
                "error_count": sum(c["severity"] == "error" for c in catalog),
                "warning_count": sum(c["severity"] == "warning" for c in catalog),
                "current": "codes",
            },
        )

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "x12_tidy_web": __version__,
            "x12_tidy": x12_tidy_version(),
            "x12_tidy_commit": x12_tidy_commit(),
        }

    @app.get("/api/formats")
    def formats() -> dict[str, Any]:
        return {"formats": available_formats()}

    @app.get("/api/codes")
    def codes() -> dict[str, Any]:
        catalog = code_catalog()
        return {
            "x12_tidy_version": x12_tidy_version(),
            "x12_tidy_commit": x12_tidy_commit(),
            "count": len(catalog),
            "codes": catalog,
        }

    @app.post("/api/validate")
    @repair_limit
    def validate(request: Request, req: ValidateRequest) -> JSONResponse:
        run = repair(req.edi, max_iterations=req.max_iterations)
        return JSONResponse(run.as_dict())

    @app.post("/api/report")
    @repair_limit
    def report(request: Request, req: ReportRequest) -> Response:
        run = repair(req.edi, max_iterations=req.max_iterations)
        rendered = render_report(run, req.format)
        return Response(
            content=rendered.content,
            media_type=rendered.media_type,
            headers={"Content-Disposition": f'attachment; filename="{rendered.filename}"'},
        )

    return app


app = create_app()

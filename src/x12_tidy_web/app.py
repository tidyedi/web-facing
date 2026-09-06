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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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


def create_app() -> FastAPI:
    app = FastAPI(
        title="x12-tidy-web",
        version=__version__,
        description="Web front end for x12-tidy: iterative X12 EDI repair with a downloadable report.",
    )

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
    def validate(req: ValidateRequest) -> JSONResponse:
        run = repair(req.edi, max_iterations=req.max_iterations)
        return JSONResponse(run.as_dict())

    @app.post("/api/report")
    def report(req: ReportRequest) -> Response:
        run = repair(req.edi, max_iterations=req.max_iterations)
        rendered = render_report(run, req.format)
        return Response(
            content=rendered.content,
            media_type=rendered.media_type,
            headers={"Content-Disposition": f'attachment; filename="{rendered.filename}"'},
        )

    return app


app = create_app()

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The FastAPI application.

Routes:

* ``GET  /``            -- the single-page form (server-rendered shell).
* ``POST /api/validate``-- run the iterative repair, return it as JSON.
* ``POST /api/report``  -- same run, streamed back as a downloadable file.
* ``GET  /api/formats`` -- the report formats on offer.
* ``GET  /api/codes``   -- every diagnostic code the installed x12-tidy emits.
* ``GET  /healthz``     -- liveness probe.

All EDI knowledge is in :mod:`x12_tidy`; the loop is in
:mod:`x12_tidy_web.engine`; this module is just wiring.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from x12_tidy_web import __version__
from x12_tidy_web.diagnostics import code_catalog
from x12_tidy_web.engine import DEFAULT_MAX_ITERATIONS, MAX_ALLOWED_ITERATIONS, repair
from x12_tidy_web.models import ReportRequest, ValidateRequest
from x12_tidy_web.reporting import available_formats, render_report

_HERE = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))


def _x12_tidy_version() -> str:
    try:
        return importlib_metadata.version("x12-tidy")
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "unknown"


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
                "x12_tidy_version": _x12_tidy_version(),
                "default_max_iterations": DEFAULT_MAX_ITERATIONS,
                "max_allowed_iterations": MAX_ALLOWED_ITERATIONS,
                "formats": available_formats(),
            },
        )

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "x12_tidy_web": __version__,
            "x12_tidy": _x12_tidy_version(),
        }

    @app.get("/api/formats")
    def formats() -> dict[str, Any]:
        return {"formats": available_formats()}

    @app.get("/api/codes")
    def codes() -> dict[str, Any]:
        catalog = code_catalog()
        return {"x12_tidy_version": _x12_tidy_version(), "count": len(catalog), "codes": catalog}

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

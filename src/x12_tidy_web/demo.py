# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""Build the static demo pages (issue #32).

``build_demo(out_dir)`` writes one self-contained HTML file per sample plus a
static copy of the ``/codes`` reference and an index. Each file inlines its CSS
and favicon, so it stands alone — hand someone a single ``.html`` and it works
with no server. Every link is either relative (between the demo files) or an
absolute URL to GitHub / TidyEDI, so nothing is broken offline.

Used by ``x12-tidy-web demo``.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from x12_tidy_web import __version__
from x12_tidy_web.diagnostics import AREA_LABELS, code_catalog, code_reference
from x12_tidy_web.engine import repair
from x12_tidy_web.provenance import x12_tidy_release, x12_tidy_source_url
from x12_tidy_web.samples import SAMPLES

_HERE = Path(__file__).parent
_TEMPLATES = _HERE / "templates"
_STATIC = _HERE / "static"
_REGISTRY_PATH = "src/x12_tidy/diagnostics/codes.py"

_VERDICTS = {
    "unrecoverable": ("fail", "Unrecoverable — no ISA line could be located."),
    "clean": ("ok", "Clean — the interchange is conformant, with nothing left to fix."),
    "residual": (
        "residual",
        "Repaired what it could — the findings below remain and x12-tidy cannot fix them automatically.",
    ),
    "unfixable": (
        "fail",
        "Not repaired — the interchange is still non-conformant. x12-tidy flagged the "
        "problems below but cannot fix them.",
    ),
    "notconverged": ("fail", "Did not converge within the pass limit — treat the output with care."),
}


def _verdict(run_dict: dict[str, Any]) -> tuple[str, str]:
    if not run_dict["recovered"]:
        return _VERDICTS["unrecoverable"]
    if run_dict["clean"]:
        return _VERDICTS["clean"]
    if run_dict["converged"]:
        return _VERDICTS["residual"] if run_dict["changed"] else _VERDICTS["unfixable"]
    return _VERDICTS["notconverged"]


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )


def _favicon_data_uri() -> str:
    raw = (_STATIC / "favicon.svg").read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")


def build_demo(out_dir: Path) -> list[Path]:
    """Render the demo bundle into ``out_dir``. Returns the files written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    env = _env()
    css = (_STATIC / "styles.css").read_text(encoding="utf-8")
    favicon = _favicon_data_uri()
    release = x12_tidy_release()
    registry_url = x12_tidy_source_url(_REGISTRY_PATH)

    nav = [(s.slug, s.title) for s in SAMPLES]
    # in the static bundle: "Demo" is this index; "Code reference" is the static
    # copy; "Repair" is the hosted app (via the landing page until it has a URL).
    static_nav = {
        "home_href": "https://tidyedi.github.io/web-facing/",
        "demo_href": "index.html",
        "codes_href": "codes.html",
    }
    written: list[Path] = []

    demo_tmpl = env.get_template("demo.html")
    for sample in SAMPLES:
        run = repair(sample.edi)
        run_dict = run.as_dict()
        verdict_class, verdict_text = _verdict(run_dict)
        html = demo_tmpl.render(
            sample=sample,
            run=run_dict,
            verdict_class=verdict_class,
            verdict_text=verdict_text,
            nav=nav,
            current=sample.slug,
            inline_css=css,
            favicon=favicon,
            app_version=__version__,
            x12_tidy_release=release,
            registry_url=registry_url,
            **static_nav,
        )
        path = out_dir / f"{sample.slug}.html"
        path.write_text(html, encoding="utf-8")
        written.append(path)

    # static /codes
    catalog = code_catalog()
    codes_html = env.get_template("codes.html").render(
        app_version=__version__,
        x12_tidy_release=release,
        registry_url=registry_url,
        codes=catalog,
        by_area=code_reference(),
        area_labels=AREA_LABELS,
        fatal_count=sum(c["severity"] == "fatal" for c in catalog),
        error_count=sum(c["severity"] == "error" for c in catalog),
        warning_count=sum(c["severity"] == "warning" for c in catalog),
        static=True,
        inline_css=css,
        favicon=favicon,
        current="codes",
        **static_nav,
    )
    codes_path = out_dir / "codes.html"
    codes_path.write_text(codes_html, encoding="utf-8")
    written.append(codes_path)

    # index
    index_html = env.get_template("demo_index.html").render(
        samples=[
            {"slug": s.slug, "title": s.title, "blurb": s.blurb} for s in SAMPLES
        ],
        inline_css=css,
        favicon=favicon,
        app_version=__version__,
        x12_tidy_release=release,
        current="demo",
        **static_nav,
    )
    index_path = out_dir / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    written.append(index_path)

    return written

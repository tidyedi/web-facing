# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""Adapt x12-tidy's :class:`~x12_tidy.diagnostics.Diagnostic` for display.

x12-tidy deliberately keeps severity *off* the ``Diagnostic`` record and
resolves it at report time from the code registry (see its ``docs/design.md``).
This module does that resolution once, up front, and flattens each finding into
a plain, JSON-friendly row (:class:`DiagnosticView`) that the report renderers
and the API can hand straight to a template or ``json.dumps``.

Nothing here decides *what* is wrong with an interchange -- that is entirely
x12-tidy's job. This is presentation only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from x12_tidy.diagnostics import Diagnostic, all_codes, meta, resolved_severity

#: Severities x12-tidy can assign, ordered most severe first. Used to sort
#: findings and to drive per-severity grouping in reports.
SEVERITY_ORDER: tuple[str, ...] = ("fatal", "error", "warning")


@dataclass(frozen=True)
class DiagnosticView:
    """One finding, with severity resolved and everything a report needs.

    ``message`` is x12-tidy's per-occurrence prose (specific to this file);
    ``title`` and ``explanation`` are the static registry text for the code.
    """

    severity: str
    code: str
    area: str
    title: str
    message: str
    explanation: str
    offset: int | None

    @property
    def severity_rank(self) -> int:
        try:
            return SEVERITY_ORDER.index(self.severity)
        except ValueError:  # unknown/future severity sorts last
            return len(SEVERITY_ORDER)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def view_diagnostic(diag: Diagnostic) -> DiagnosticView:
    """Resolve one x12-tidy ``Diagnostic`` into a :class:`DiagnosticView`."""
    code_meta = meta(diag.code)
    return DiagnosticView(
        severity=resolved_severity(diag.code),
        code=diag.code.value,
        area=diag.code.area,
        title=code_meta.title,
        message=diag.message,
        explanation=code_meta.explanation,
        offset=diag.offset,
    )


def view_diagnostics(diags: list[Diagnostic]) -> list[DiagnosticView]:
    """Resolve a list of findings, most severe first, then by byte offset."""
    views = [view_diagnostic(d) for d in diags]
    views.sort(key=lambda v: (v.severity_rank, v.offset if v.offset is not None else -1))
    return views


def severity_counts(views: list[DiagnosticView]) -> dict[str, int]:
    """Count findings per severity, always including every key in order."""
    counts = {sev: 0 for sev in SEVERITY_ORDER}
    for v in views:
        counts[v.severity] = counts.get(v.severity, 0) + 1
    return counts


def code_catalog() -> list[dict[str, Any]]:
    """Every diagnostic code x12-tidy can emit -- for a reference page.

    Pulled live from the installed x12-tidy so it never drifts from the version
    actually doing the work.
    """
    catalog: list[dict[str, Any]] = []
    for code in all_codes():
        code_meta = meta(code)
        catalog.append(
            {
                "code": code.value,
                "area": code.area,
                "severity": resolved_severity(code),
                "title": code_meta.title,
                "explanation": code_meta.explanation,
                "deprecated": code_meta.deprecated,
            }
        )
    catalog.sort(key=lambda c: (c["area"], c["code"]))
    return catalog

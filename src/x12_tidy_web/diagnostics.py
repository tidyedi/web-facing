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
from urllib.parse import urlencode

from x12_tidy.diagnostics import AREAS, Diagnostic, all_codes, meta, resolved_severity

#: Severities x12-tidy can assign, ordered most severe first. Used to sort
#: findings and to drive per-severity grouping in reports.
SEVERITY_ORDER: tuple[str, ...] = ("fatal", "error", "warning")

#: Where a reader disputes a code's severity/wording/coverage. The codes are
#: x12-tidy's (see "the one rule" in CLAUDE.md), so the conversation belongs on
#: x12-tidy, not here -- issue #25. Q&A category so a maintainer can mark an
#: answer.
_DISCUSS_NEW = "https://github.com/tidyedi/x12-tidy/discussions/new"
_DISCUSS_CATEGORY = "q-a"

@dataclass(frozen=True)
class SeverityInfo:
    """Static, code-independent prose describing one severity bucket.

    The single source for the severity legend: the ``/codes`` reference
    (every entry, always), and the results page, which shows a pass only the
    entries for severities that pass's findings actually used (see
    :func:`severity_legend_for` and ``static/app.js``'s ``renderPassLegend``,
    which reads the same data embedded as JSON on the page).
    """

    severity: str
    label: str
    description: str


#: One entry per :data:`SEVERITY_ORDER` value, in that order. The wording was
#: checked against every code in the installed registry (issue #73); if a
#: registry bump changes which bucket a code sits in, re-check it here.
SEVERITY_META: dict[str, SeverityInfo] = {
    "fatal": SeverityInfo(
        severity="fatal",
        label="fatal",
        description=(
            "x12-tidy cannot produce an interchange you can rely on. Either the "
            "structure can't be parsed — a delimiter missing or ambiguous, the "
            "ISA line malformed or not locatable — or the envelope fails its "
            "own integrity checks: a required GE / SE / IEA missing, a segment "
            "outside the envelope, or a count or control number malformed, "
            "non-unique, or not agreeing (ISA13 vs IEA02, GS08 vs ISA12, a "
            "stated count vs the segments actually present). x12-tidy reports "
            "these but will not guess the fix, and a conforming receiver "
            "rejects the interchange. Fix the source data and repair again."
        ),
    ),
    "error": SeverityInfo(
        severity="error",
        label="error",
        description=(
            "A real conformance violation in a specific element or segment — "
            "the value or structure breaks an X12 rule, though x12-tidy can "
            "still read the interchange (an ISA element off its fixed width, a "
            "lowercased segment identifier, an unusable delimiter, an ISA15 "
            "that isn't T/P/I). x12-tidy fixes what it can do safely and flags "
            "the rest. Review every one — some are not auto-fixed, and a "
            "couple turn fatal if the interchange actually uses the affected "
            "feature (composite elements, repetition)."
        ),
    ),
    "warning": SeverityInfo(
        severity="warning",
        label="warning",
        description=(
            "Something about the input was off, but x12-tidy could resolve it "
            "on its own without risking a real data value — bytes stripped "
            "from before the ISA or after the segment terminator, a UTF-16 "
            "file transcoded to single-byte, a stray newline inside an ISA "
            "element replaced with a space, an unrecognised ISA12 version left "
            "opaque. The interchange is otherwise sound. Treat each as a trust "
            "signal: usually a harmless sender quirk, occasionally a sign the "
            "file was corrupted or mishandled upstream — confirm the cleanup "
            "is what you expected."
        ),
    ),
}


def severity_legend_for(severities: set[str] | None = None) -> list[dict[str, str]]:
    """:data:`SEVERITY_META`, in :data:`SEVERITY_ORDER`, as plain dicts for a
    template or a JSON payload. ``severities`` restricts it to just those
    keys (a single pass's own findings); omit it for the full reference
    legend (``/codes``, and every severity a pass could possibly carry, for
    the JSON the live app embeds and filters client-side per pass)."""
    return [
        {"severity": sev, "label": SEVERITY_META[sev].label, "description": SEVERITY_META[sev].description}
        for sev in SEVERITY_ORDER
        if severities is None or sev in severities
    ]


#: Display headings for x12-tidy's closed ``area`` vocabulary -- just the
#: abbreviation spelled out, so the reference page can group codes. The areas
#: themselves are x12-tidy's (:data:`x12_tidy.diagnostics.AREAS`); if that tuple
#: grows, an unmapped area falls back to its bare name.
AREA_LABELS: dict[str, str] = {
    "isa": "ISA — interchange header",
    "gs": "GS — functional-group envelope",
    "st": "ST — transaction-set envelope",
    "delimiter": "Delimiters",
    "structure": "Structure & control counts",
}


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


def _discuss_url(code: str, severity: str, area: str, title: str) -> str:
    """A pre-filled "new discussion" URL on x12-tidy for challenging one code."""
    body = (
        f"Diagnostic: `{code}`  (severity: {severity}, area: `{area}`)\n"
        f"Registry title: {title}\n\n"
        "What's your feedback — do you agree, disagree, or is there a case this "
        "misses?\n"
    )
    query = urlencode({"category": _DISCUSS_CATEGORY, "title": f"{code}: ", "body": body})
    return f"{_DISCUSS_NEW}?{query}"


def code_catalog() -> list[dict[str, Any]]:
    """Every diagnostic code x12-tidy can emit -- for a reference page.

    Pulled live from the installed x12-tidy so it never drifts from the version
    actually doing the work. ``discuss_url`` opens a pre-filled discussion on the
    x12-tidy repo (issue #25).
    """
    catalog: list[dict[str, Any]] = []
    for code in all_codes():
        code_meta = meta(code)
        severity = resolved_severity(code)
        catalog.append(
            {
                "code": code.value,
                "area": code.area,
                "severity": severity,
                "title": code_meta.title,
                "explanation": code_meta.explanation,
                "deprecated": code_meta.deprecated,
                "discuss_url": _discuss_url(code.value, severity, code.area, code_meta.title),
            }
        )
    catalog.sort(key=lambda c: (c["area"], c["code"]))
    return catalog


def code_reference() -> list[tuple[str, list[dict[str, Any]]]]:
    """:func:`code_catalog` grouped by area, in x12-tidy's ``AREAS`` order.

    For the ``/codes`` reference page. Areas x12-tidy defines but has no code
    for yet are omitted; any area outside :data:`AREAS` sorts to the end.
    """
    catalog = code_catalog()
    order = {area: i for i, area in enumerate(AREAS)}
    areas_seen = sorted({c["area"] for c in catalog}, key=lambda a: order.get(a, len(order)))
    return [(area, [c for c in catalog if c["area"] == area]) for area in areas_seen]

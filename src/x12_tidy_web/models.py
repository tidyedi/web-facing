# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""Pydantic schemas for the JSON API.

Kept intentionally thin: the request models validate and clamp user input, and
the response is the plain dict from :meth:`RepairRun.as_dict`, so the wire shape
has exactly one definition (in :mod:`x12_tidy_web.engine`) and this file never
drifts from it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from x12_tidy_web.engine import (
    DEFAULT_MAX_ITERATIONS,
    MAX_ALLOWED_ITERATIONS,
)
from x12_tidy_web.reporting import FORMATS

#: Reject anything larger than this up front (bytes of submitted EDI text).
#: One interchange is rarely over ~100 KB; this is generous and bounds abuse.
MAX_EDI_CHARS = 2_000_000


class ValidateRequest(BaseModel):
    edi: str = Field(..., description="The X12 interchange text to validate and repair.")
    max_iterations: int = Field(
        default=DEFAULT_MAX_ITERATIONS,
        ge=1,
        le=MAX_ALLOWED_ITERATIONS,
        description="Safety cap on repair passes.",
    )

    @field_validator("edi")
    @classmethod
    def _not_empty_not_huge(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("no EDI text was provided")
        if len(value) > MAX_EDI_CHARS:
            raise ValueError(f"input exceeds the {MAX_EDI_CHARS:,}-character limit")
        return value


class ReportRequest(ValidateRequest):
    format: str = Field(default="json", description=f"One of: {', '.join(FORMATS)}")

    @field_validator("format")
    @classmethod
    def _known_format(cls, value: str) -> str:
        v = value.lower().strip()
        if v not in FORMATS:
            raise ValueError(f"unknown format {value!r}; choose one of {', '.join(FORMATS)}")
        return v

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""Shared fixtures."""

from __future__ import annotations

import pytest

# A clean 850 interchange: correct ISA widths, matching control counts.
CLEAN_EDI = (
    b"ISA*00*          *00*          *ZZ*ACME           *ZZ*WIDGETCO       "
    b"*240101*1200*U*00401*000000001*0*P*:~"
    b"GS*PO*ACME*WIDGET*20240101*1200*1*X*004010~"
    b"ST*850*0001~BEG*00*NE*PO123**20240101~SE*3*0001~"
    b"GE*1*1~IEA*1*000000001~"
)

# Same interchange, three defects: leading bytes, short ISA06/ISA08, IEA01 says 2.
DIRTY_EDI = (
    b"Subject: FW: your order\r\n\r\n"
    b"ISA*00*   *00*   *ZZ*ACME*ZZ*WIDGETCO*240101*1200*U*00401*000000001*0*P*:~"
    b"GS*PO*ACME*WIDGET*20240101*1200*1*X*004010~"
    b"ST*850*0001~BEG*00*NE*PO123**20240101~SE*3*0001~"
    b"GE*1*1~IEA*2*000000001~"
)

NOT_EDI = b"this is not an EDI file at all, not even close"


@pytest.fixture
def clean_edi() -> bytes:
    return CLEAN_EDI


@pytest.fixture
def dirty_edi() -> bytes:
    return DIRTY_EDI


@pytest.fixture
def not_edi() -> bytes:
    return NOT_EDI


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    from x12_tidy_web.app import create_app

    # Rate limiting is exercised in its own tests; keep it out of the way here.
    monkeypatch.setenv("X12_TIDY_WEB_RATE_LIMIT", "off")
    return TestClient(create_app())

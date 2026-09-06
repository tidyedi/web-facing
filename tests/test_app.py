# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The HTTP layer."""

from __future__ import annotations

import json

CLEAN = (
    "ISA*00*          *00*          *ZZ*ACME           *ZZ*WIDGETCO       "
    "*240101*1200*U*00401*000000001*0*P*:~"
    "GS*PO*ACME*WIDGET*20240101*1200*1*X*004010~"
    "ST*850*0001~BEG*00*NE*PO123**20240101~SE*3*0001~"
    "GE*1*1~IEA*1*000000001~"
)
DIRTY = (
    "Subject: FW\r\n\r\nISA*00*   *00*   *ZZ*ACME*ZZ*WIDGETCO*240101*1200*U*00401"
    "*000000001*0*P*:~GS*PO*ACME*WIDGET*20240101*1200*1*X*004010~ST*850*0001~"
    "BEG*00*NE*PO123**20240101~SE*3*0001~GE*1*1~IEA*2*000000001~"
)


def test_index_page_renders(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "x12-tidy" in resp.text
    assert "Validate" in resp.text


def test_healthz(client) -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["x12_tidy"] != "unknown"
    # Installed from git in every supported environment, so the commit is pinned.
    assert isinstance(body["x12_tidy_commit"], str)
    assert len(body["x12_tidy_commit"]) == 40


def test_validate_clean(client) -> None:
    resp = client.post("/api/validate", json={"edi": CLEAN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["clean"] is True
    assert body["stop_reason"] == "clean"
    assert body["changed"] is False


def test_validate_dirty(client) -> None:
    body = client.post("/api/validate", json={"edi": DIRTY, "max_iterations": 5}).json()
    assert body["recovered"] is True
    assert body["changed"] is True
    assert body["clean"] is False
    assert body["residual_severity_counts"]["fatal"] >= 1
    codes = {d["code"] for it in body["iterations"] for d in it["diagnostics"]}
    assert "isa.leading-bytes" in codes


def test_validate_rejects_empty(client) -> None:
    resp = client.post("/api/validate", json={"edi": "   "})
    assert resp.status_code == 422


def test_validate_rejects_bad_iterations(client) -> None:
    assert client.post("/api/validate", json={"edi": CLEAN, "max_iterations": 0}).status_code == 422
    assert client.post("/api/validate", json={"edi": CLEAN, "max_iterations": 99}).status_code == 422


def test_report_download_markdown(client) -> None:
    resp = client.post("/api/report", json={"edi": DIRTY, "format": "markdown"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.headers["content-disposition"].endswith('.md"')
    assert "# EDI validation report" in resp.text


def test_report_download_json(client) -> None:
    resp = client.post("/api/report", json={"edi": DIRTY, "format": "json"})
    assert resp.status_code == 200
    doc = json.loads(resp.text)
    assert doc["schema"] == "x12-tidy-web/repair-run/1"


def test_report_rejects_unknown_format(client) -> None:
    resp = client.post("/api/report", json={"edi": DIRTY, "format": "yaml"})
    assert resp.status_code == 422


def test_formats_endpoint(client) -> None:
    body = client.get("/api/formats").json()
    keys = {f["key"] for f in body["formats"]}
    assert {"json", "markdown", "html", "text", "csv"} <= keys


def test_codes_endpoint(client) -> None:
    body = client.get("/api/codes").json()
    assert body["count"] > 0
    assert body["count"] == len(body["codes"])
    assert len(body["x12_tidy_commit"]) == 40
    sample = body["codes"][0]
    assert {"code", "area", "severity", "title"} <= sample.keys()


def test_index_footer_shows_x12_tidy_commit(client) -> None:
    text = client.get("/").text
    assert "x12-tidy 0.1.0 (git " in text


def test_index_has_privacy_callout_and_severity_legend(client) -> None:
    text = client.get("/").text
    assert "stored, logged, or sent anywhere" in text
    assert 'class="legend"' in text
    for sev in ("FATAL", "ERROR", "WARNING"):
        assert sev in text


def test_codes_page_renders(client) -> None:
    resp = client.get("/codes")
    assert resp.status_code == 200
    text = resp.text
    # A real code, its area heading, and the severity styling all present.
    assert "isa.leading-bytes" in text
    assert "ISA — interchange header" in text
    assert 'class="sev fatal"' in text
    # Reference is read from the installed x12-tidy, credited to its registry.
    assert "0.1.0 (git " in text
    assert "diagnostic registry" in text

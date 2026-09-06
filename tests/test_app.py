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
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(sample["discuss_url"])
    assert parsed.netloc == "github.com"
    assert parsed.path == "/tidyedi/x12-tidy/discussions/new"
    q = parse_qs(parsed.query)
    assert q["category"] == ["q-a"]
    assert sample["code"] in q["title"][0]
    assert sample["code"] in q["body"][0]


def test_index_footer_shows_x12_tidy_commit(client) -> None:
    text = client.get("/").text
    assert "x12-tidy 0.1.0 (git " in text


def test_index_has_privacy_callout_and_severity_legend(client) -> None:
    text = client.get("/").text
    assert "stored, logged, or sent anywhere" in text
    assert 'class="legend"' in text
    for sev in ("fatal", "error", "warning"):
        assert f'class="pill {sev}"' in text


def test_favicon_and_brand_mark_are_served(client) -> None:
    assert 'rel="icon"' in client.get("/").text
    svg = client.get("/static/favicon.svg")
    assert svg.status_code == 200
    assert svg.headers["content-type"].startswith("image/svg")


def test_codes_page_renders(client) -> None:
    resp = client.get("/codes")
    assert resp.status_code == 200
    text = resp.text
    # A real code, its area heading, and the severity styling all present.
    assert "isa.leading-bytes" in text
    assert "ISA — interchange header" in text
    assert 'class="sev fatal"' in text
    # Reference is read from the installed x12-tidy, credited + linked to source.
    assert "0.1.0 (git " in text
    assert "diagnostic code registry" in text
    assert "github.com/tidyedi/x12-tidy/blob/" in text
    assert "diagnostics/codes.py" in text
    # per-code "Discuss" links into x12-tidy's discussions (#25)
    assert text.count(">Discuss ↗<") == len(client.get("/api/codes").json()["codes"])
    assert "x12-tidy/discussions/new?" in text


def test_codes_page_has_a_severity_filter(client) -> None:
    text = client.get("/codes").text
    assert 'class="codes-filter"' in text
    for sev in ("fatal", "error", "warning"):
        assert f'data-sev="{sev}"' in text
    # every code row is tagged so the filter can show/hide it
    api = client.get("/api/codes").json()["codes"]
    assert text.count("<tr data-sev=") == len(api)


def test_index_links_and_byte_note(client) -> None:
    text = client.get("/").text
    # the shared nav appears twice — a top bar and in the footer
    assert text.count('class="navlinks"') == 2
    assert 'class="navbar"' in text
    assert "https://docs.tidyedi.com" in text
    assert "tidyedi.com" not in text.replace("docs.tidyedi.com", "")  # the dead bare domain is gone
    assert "github.com/tidyedi/x12-tidy/blob/" in text  # registry link in the passes note
    assert "The <strong>Byte</strong> column" in text


def _fresh_client(monkeypatch, limit: str):
    from fastapi.testclient import TestClient

    from x12_tidy_web.app import create_app

    monkeypatch.setenv("X12_TIDY_WEB_RATE_LIMIT", limit)
    return TestClient(create_app())


def test_repair_endpoints_are_rate_limited(monkeypatch) -> None:
    c = _fresh_client(monkeypatch, "5/minute")
    statuses = [c.post("/api/validate", json={"edi": CLEAN}).status_code for _ in range(8)]
    assert statuses.count(200) == 5
    assert 429 in statuses

    blocked = c.post("/api/report", json={"edi": CLEAN, "format": "json"})
    assert blocked.status_code == 429  # shared budget across both repair endpoints
    assert "Retry-After" in blocked.headers
    assert "rate limit" in blocked.text.lower()

    assert c.get("/healthz").status_code == 200  # GET routes stay open


def test_rate_limit_can_be_turned_off(monkeypatch) -> None:
    c = _fresh_client(monkeypatch, "off")
    statuses = [c.post("/api/validate", json={"edi": CLEAN}).status_code for _ in range(12)]
    assert set(statuses) == {200}


def test_index_has_the_segment_outline_and_config(client) -> None:
    text = client.get("/").text
    assert 'id="exploded-wrap"' in text
    assert "Read it segment by segment" in text
    assert 'id="app-config"' in text


def _app_config(html: str) -> dict:
    blob = html.split('id="app-config">', 1)[1].split("</script>", 1)[0]
    return json.loads(blob)


def test_report_a_wrong_result_link_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("X12_TIDY_WEB_FEEDBACK_EMAIL", raising=False)
    off = _fresh_client(monkeypatch, "off")
    assert _app_config(off.get("/").text)["feedbackEmail"] == ""

    monkeypatch.setenv("X12_TIDY_WEB_FEEDBACK_EMAIL", "ops@example.com")
    on = _fresh_client(monkeypatch, "off")
    assert _app_config(on.get("/").text)["feedbackEmail"] == "ops@example.com"


def test_index_embeds_the_samples(client) -> None:
    import json

    text = client.get("/").text
    assert "Load a random sample" in text
    blob = text.split('id="samples-data">', 1)[1].split("</script>", 1)[0]
    samples = json.loads(blob)
    assert len(samples) == 5
    assert {"forwarded-email", "pipe-delimited", "wrapped-isa"} <= {s["slug"] for s in samples}
    assert all(s["edi"] and s["blurb"] for s in samples)

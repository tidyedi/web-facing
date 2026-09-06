# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""Report renderers."""

from __future__ import annotations

import json

import pytest

from x12_tidy_web.engine import repair
from x12_tidy_web.reporting import FORMATS, available_formats, render_report


@pytest.fixture
def dirty_run(dirty_edi: bytes):
    return repair(dirty_edi)


@pytest.fixture
def broken_run(not_edi: bytes):
    return repair(not_edi)


@pytest.mark.parametrize("fmt", sorted(FORMATS))
def test_every_format_renders_nonempty(dirty_run, fmt: str) -> None:
    report = render_report(dirty_run, fmt)
    assert report.content
    assert report.media_type == FORMATS[fmt][0]
    assert report.filename.endswith("." + FORMATS[fmt][1])


@pytest.mark.parametrize("fmt", sorted(FORMATS))
def test_every_format_handles_unrecoverable(broken_run, fmt: str) -> None:
    # No payload, no facts — renderers must not crash.
    assert render_report(broken_run, fmt).content


def test_json_report_is_valid_and_annotated(dirty_run) -> None:
    doc = json.loads(render_report(dirty_run, "json").content)
    assert doc["schema"] == "x12-tidy-web/repair-run/1"
    assert "generated_at" in doc
    assert doc["generator"].startswith("x12-tidy-web")
    # The x12-tidy build that produced the run, so a saved report is traceable.
    assert doc["x12_tidy"]["version"] == "0.1.0"
    assert len(doc["x12_tidy"]["commit"]) == 40
    assert doc["x12_tidy"]["release"].startswith("0.1.0 (git ")


@pytest.mark.parametrize("fmt", ["markdown", "text", "html"])
def test_prose_reports_credit_the_x12_tidy_build(dirty_run, fmt: str) -> None:
    text = render_report(dirty_run, fmt).content.decode()
    assert "x12-tidy 0.1.0 (git " in text


def test_markdown_report_mentions_key_facts(dirty_run) -> None:
    text = render_report(dirty_run, "markdown").content.decode()
    assert "# EDI validation report" in text
    assert "## Passes" in text
    assert "isa.element-width" in text
    assert "## Corrected interchange" in text


def test_csv_report_has_one_row_per_finding(dirty_run) -> None:
    import csv
    import io

    rows = list(csv.reader(io.StringIO(render_report(dirty_run, "csv").content.decode())))
    header, *body = rows
    assert header == ["pass", "severity", "code", "area", "byte_offset", "title", "message"]
    expected = sum(len(it.diagnostics) for it in dirty_run.iterations)
    assert len(body) == expected


def test_html_report_is_escaped(dirty_run) -> None:
    html_text = render_report(dirty_run, "html").content.decode()
    assert html_text.startswith("<!doctype html>")
    assert "<script>" not in html_text.lower().replace("<script src", "")


def test_unknown_format_raises(dirty_run) -> None:
    with pytest.raises(ValueError):
        render_report(dirty_run, "yaml")


def test_available_formats_shape() -> None:
    formats = available_formats()
    assert {f["key"] for f in formats} == set(FORMATS)
    for f in formats:
        assert f["label"] and f["media_type"] and f["extension"]

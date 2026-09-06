# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The static demo bundle (`x12-tidy-web demo`)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from x12_tidy_web.demo import build_demo
from x12_tidy_web.samples import SAMPLES


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("demo")
    build_demo(out)
    return out


def test_writes_a_page_per_sample_plus_codes_and_index(bundle: Path) -> None:
    names = {p.name for p in bundle.iterdir()}
    assert names == {f"{s.slug}.html" for s in SAMPLES} | {"codes.html", "index.html"}


@pytest.mark.parametrize("name", ["forwarded-email.html", "pipe-delimited.html", "codes.html", "index.html"])
def test_each_file_is_self_contained(bundle: Path, name: str) -> None:
    html = (bundle / name).read_text(encoding="utf-8")
    assert "<style>" in html  # CSS inlined
    assert "data:image/svg+xml;base64," in html  # favicon inlined
    assert "url_for" not in html  # no server-only template helper leaked
    assert not re.search(r"{[{%]", html)  # no unrendered Jinja
    assert "jinja2.exceptions" not in html


def test_verdicts_match_the_samples(bundle: Path) -> None:
    fwd = (bundle / "forwarded-email.html").read_text()
    assert "verdict residual" in fwd
    assert "structure.functional-group-count-mismatch" in fwd
    assert "Forwarded email" in fwd

    pipe = (bundle / "pipe-delimited.html").read_text()
    assert "verdict ok" in pipe
    assert "Clean — the interchange is conformant, with nothing left to fix." in pipe


def test_links_between_pages_are_relative(bundle: Path) -> None:
    fwd = (bundle / "forwarded-email.html").read_text()
    assert 'href="codes.html"' in fwd
    assert 'href="index.html"' in fwd
    assert 'href="pipe-delimited.html"' in fwd
    # external links absolute
    assert 'href="https://github.com/tidyedi/web-facing"' in fwd

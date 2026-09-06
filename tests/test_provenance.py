# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The x12-tidy build identifiers surfaced in the UI, API, CLI and reports."""

from __future__ import annotations

import json
import re
from importlib.metadata import distribution

from x12_tidy_web.provenance import x12_tidy_commit, x12_tidy_release, x12_tidy_version

_SHA40 = re.compile(r"\A[0-9a-f]{40}\Z")


def test_version_is_the_package_version() -> None:
    assert x12_tidy_version() == "0.1.0"


def test_commit_matches_the_installed_distribution_metadata() -> None:
    origin = json.loads(distribution("x12-tidy").read_text("direct_url.json") or "{}")
    expected = origin["vcs_info"]["commit_id"]

    commit = x12_tidy_commit()
    assert commit == expected
    assert _SHA40.match(commit) is not None


def test_release_combines_version_and_short_sha() -> None:
    commit = x12_tidy_commit()
    assert commit is not None
    assert x12_tidy_release() == f"0.1.0 (git {commit[:7]})"

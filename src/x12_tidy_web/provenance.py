# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""Which build of x12-tidy is installed.

When a repaired interchange or a finding looks wrong, the first question is
always *which* x12-tidy produced it -- the bug belongs either to x12-tidy (the
X12 logic) or to this repo (the loop, the report, the HTTP layer). See
CLAUDE.md "The one rule" and ``tests/test_dependency_provenance.py``.

x12-tidy is pinned to a moving branch (``git+https://…@main``), so its package
version has read ``0.1.0`` since its first commit and tells you nothing. The git
commit is the part that moves. These helpers dig it out of the distribution
metadata (``direct_url.json``, written by the installer for any VCS/URL install)
so it can be shown in the page footer, ``/healthz``, ``/api/codes``, the CLI
``--version`` banner, and every downloaded report.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
from functools import lru_cache

_DIST = "x12-tidy"
_UNKNOWN = "unknown"


@lru_cache(maxsize=1)
def x12_tidy_version() -> str:
    """The installed x12-tidy package version, or ``"unknown"`` if absent.

    Currently always ``"0.1.0"`` for a real install -- kept as its own field so
    machine consumers have a stable key even once x12-tidy starts versioning.
    """
    try:
        return importlib_metadata.version(_DIST)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover - install is a test dep
        return _UNKNOWN


@lru_cache(maxsize=1)
def x12_tidy_commit() -> str | None:
    """The full git commit SHA x12-tidy was installed from, or ``None``.

    ``None`` means the metadata carries no VCS info -- x12-tidy is not installed,
    or (against the project rules) came from a local path rather than git.
    """
    try:
        raw = importlib_metadata.distribution(_DIST).read_text("direct_url.json")
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover - install is a test dep
        return None
    if not raw:
        return None
    vcs_info = json.loads(raw).get("vcs_info")
    if not isinstance(vcs_info, dict):
        return None
    commit = vcs_info.get("commit_id")
    return commit if isinstance(commit, str) and commit else None


@lru_cache(maxsize=1)
def x12_tidy_release() -> str:
    """A one-line, human-readable identifier for the installed x12-tidy build.

    ``"0.1.0 (git 04bffa4)"`` for the normal git install, ``"0.1.0"`` if the VCS
    metadata is missing, ``"unknown"`` if x12-tidy is not installed at all. This
    is the string to drop into a footer or a report so a screenshot pins the
    exact build.
    """
    version = x12_tidy_version()
    commit = x12_tidy_commit()
    if commit is None:
        return version
    return f"{version} (git {commit[:7]})"

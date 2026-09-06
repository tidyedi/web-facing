# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""Guardrails for the one rule: x12-tidy is imported from its git repo, never
copied or path-linked into this one.

Why this file exists (see tidyedi/web-facing#13): a vendored or locally
path-linked copy of x12-tidy silently stops tracking upstream. The web app would
then repair EDI with stale rules — wrong output that still looks plausible. These
tests fail loudly the moment that happens, in CI and locally.

If you are deliberately testing against unreleased x12-tidy work, push it to a
branch and point the ``git+https://…@<branch>`` ref at it. Do not add a
``[tool.uv.sources]`` path entry.
"""

from __future__ import annotations

import json
import tomllib
from importlib.metadata import distribution
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
X12_TIDY_REPO = "github.com/tidyedi/x12-tidy"


def _pyproject() -> dict[str, object]:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_x12_tidy_is_installed_from_its_git_repo() -> None:
    """The installed distribution must carry VCS provenance, not a local path."""
    raw = distribution("x12-tidy").read_text("direct_url.json")
    assert raw is not None, "x12-tidy has no direct_url.json — not installed from a URL"
    origin = json.loads(raw)

    assert "vcs_info" in origin, f"x12-tidy was not installed from a VCS: {origin}"
    assert origin["vcs_info"]["vcs"] == "git"
    assert X12_TIDY_REPO in origin["url"], origin["url"]

    # A `uv` editable/path install records dir_info (often {"editable": true}).
    assert "dir_info" not in origin, f"x12-tidy is path-linked, not imported: {origin}"


def test_imported_x12_tidy_is_not_inside_this_repo() -> None:
    """The module we import must live in site-packages, not our source tree."""
    import x12_tidy

    module_path = Path(x12_tidy.__file__).resolve()
    assert "site-packages" in module_path.parts, module_path
    assert not module_path.is_relative_to(REPO_ROOT / "src"), (
        f"x12-tidy is vendored under src/: {module_path}"
    )


def test_pyproject_pins_x12_tidy_to_a_git_ref() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    deps = project["dependencies"]
    assert isinstance(deps, list)

    x12_reqs = [d for d in deps if isinstance(d, str) and d.startswith("x12-tidy")]
    assert len(x12_reqs) == 1, x12_reqs
    assert x12_reqs[0].startswith("x12-tidy @ git+https://"), x12_reqs[0]
    assert X12_TIDY_REPO in x12_reqs[0], x12_reqs[0]


def test_pyproject_has_no_path_source_for_x12_tidy() -> None:
    """No `[tool.uv.sources]` entry may redirect x12-tidy to a local checkout."""
    tool = _pyproject().get("tool", {})
    assert isinstance(tool, dict)
    sources = tool.get("uv", {})
    assert isinstance(sources, dict)
    uv_sources = sources.get("sources", {})
    assert isinstance(uv_sources, dict)
    assert "x12-tidy" not in uv_sources and "x12_tidy" not in uv_sources, (
        f"[tool.uv.sources] redirects x12-tidy: {uv_sources}"
    )


def test_no_vendored_x12_tidy_package_in_tree() -> None:
    """No copy of the x12_tidy package may be checked in anywhere under the repo."""
    offenders = [
        p
        for p in REPO_ROOT.rglob("x12_tidy")
        if p.is_dir() and ".venv" not in p.parts and ".git" not in p.parts
    ]
    assert not offenders, f"vendored x12_tidy package(s) found: {offenders}"

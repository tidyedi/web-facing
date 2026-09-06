# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The bundled broken samples."""

from __future__ import annotations

import pytest

from x12_tidy_web.engine import repair
from x12_tidy_web.samples import SAMPLES, by_slug, random_sample


def test_five_samples_with_unique_slugs() -> None:
    assert len(SAMPLES) == 5
    assert len({s.slug for s in SAMPLES}) == 5
    for s in SAMPLES:
        assert s.title and s.blurb and s.edi


def test_by_slug_round_trips() -> None:
    for s in SAMPLES:
        assert by_slug(s.slug) is s
    with pytest.raises(KeyError):
        by_slug("nope")


def test_random_sample_can_exclude_the_last_one() -> None:
    assert random_sample() in SAMPLES
    for _ in range(20):
        assert random_sample(exclude="forwarded-email").slug != "forwarded-email"


@pytest.mark.parametrize(
    ("slug", "stop_reason", "clean"),
    [
        ("forwarded-email", "stable", False),  # residual functional-group-count-mismatch
        ("pipe-delimited", "clean", True),
        ("lowercased-isa", "clean", True),
        ("truncated-transmission", "stable", False),  # missing trailers, unfixable
        ("wrapped-isa", "clean", True),
    ],
)
def test_each_sample_repairs_to_its_documented_outcome(
    slug: str, stop_reason: str, clean: bool
) -> None:
    run = repair(by_slug(slug).edi)
    assert run.recovered
    assert run.stop_reason == stop_reason
    assert run.clean is clean


def test_forwarded_email_leaves_exactly_the_count_mismatch() -> None:
    run = repair(by_slug("forwarded-email").edi)
    residual = {(d.severity, d.code) for d in run.iterations[-1].diagnostics}
    assert residual == {("fatal", "structure.functional-group-count-mismatch")}

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The iterative-repair loop."""

from __future__ import annotations

from x12_tidy_web.engine import MAX_ALLOWED_ITERATIONS, repair


def test_clean_input_converges_in_one_pass(clean_edi: bytes) -> None:
    run = repair(clean_edi)
    assert run.stop_reason == "clean"
    assert run.converged and run.recovered and run.clean
    assert len(run.iterations) == 1
    assert run.iterations[0].was_clean
    assert not run.changed


def test_dirty_input_is_repaired_and_reports_residual(dirty_edi: bytes) -> None:
    run = repair(dirty_edi)

    assert run.recovered
    assert run.changed
    assert run.final_text is not None and run.final_text.startswith("ISA*")
    # The email header is gone from the corrected output.
    assert "Subject:" not in run.final_text

    # First pass does the structural work; it changed the interchange.
    assert run.iterations[0].changed
    codes_pass1 = {d.code for d in run.iterations[0].diagnostics}
    assert "isa.leading-bytes" in codes_pass1
    assert "isa.element-width" in codes_pass1

    # It stabilises: the control-count mismatch cannot be auto-fixed.
    assert run.stop_reason == "stable"
    residual = {d.code for d in run.residual_diagnostics}
    assert any("count-mismatch" in c for c in residual)
    assert run.residual_severity_counts["fatal"] >= 1
    assert not run.clean


def test_verdict_reads_as_unfixable_when_a_fatal_finding_remains(dirty_edi: bytes) -> None:
    # dirty_edi stabilises with a fatal control-count mismatch. However much
    # structural cleanup passed 1 did, any residual fatal must dominate the
    # verdict: a conforming parser rejects it and x12-tidy will not guess.
    run = repair(dirty_edi)
    assert run.residual_severity_counts["fatal"] >= 1
    v = run.verdict
    assert v["state"] == "unfixable"
    assert v["css_class"] == "fail"
    assert v["headline"].startswith("Cannot be repaired")
    assert "fatal" in v["headline"]
    assert run.as_dict()["verdict"] == v


def test_verdict_clean_and_unrecoverable(clean_edi: bytes, not_edi: bytes) -> None:
    assert repair(clean_edi).verdict["state"] == "clean"
    assert repair(clean_edi).verdict["css_class"] == "ok"
    assert repair(not_edi).verdict["state"] == "unrecoverable"
    assert repair(not_edi).verdict["css_class"] == "fail"


def test_second_pass_does_not_change_bytes(dirty_edi: bytes) -> None:
    run = repair(dirty_edi)
    assert len(run.iterations) == 2
    assert run.iterations[1].changed is False
    assert run.iterations[1].input_text == run.iterations[0].output_text


def test_unrecoverable_input(not_edi: bytes) -> None:
    run = repair(not_edi)
    assert run.stop_reason == "unrecoverable"
    assert not run.recovered
    assert run.final_text is None
    assert run.final_facts is None
    assert len(run.iterations) == 1
    assert run.iterations[0].output_text is None
    assert run.residual_diagnostics  # a fatal explaining why


def test_accepts_str_and_bytes_equivalently(dirty_edi: bytes) -> None:
    from_bytes = repair(dirty_edi)
    from_text = repair(dirty_edi.decode("latin-1"))
    assert from_bytes.final_text == from_text.final_text
    assert from_bytes.stop_reason == from_text.stop_reason


def test_max_iterations_is_clamped(clean_edi: bytes) -> None:
    assert repair(clean_edi, max_iterations=0).max_iterations == 1
    assert repair(clean_edi, max_iterations=9999).max_iterations == MAX_ALLOWED_ITERATIONS


def test_as_dict_is_json_serialisable(dirty_edi: bytes) -> None:
    import json

    doc = repair(dirty_edi).as_dict()
    round_tripped = json.loads(json.dumps(doc))
    assert round_tripped["schema"] == "x12-tidy-web/repair-run/1"
    assert round_tripped["iteration_count"] == len(round_tripped["iterations"])
    assert round_tripped["changed"] is True


def test_facts_are_decoded_strings(dirty_edi: bytes) -> None:
    facts = repair(dirty_edi).final_facts
    assert facts is not None
    assert facts.sender_id == "ACME"  # decoded and stripped
    assert facts.functional_group_count == 1

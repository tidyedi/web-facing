# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The iterative-repair loop.

x12-tidy's :func:`x12_tidy.tidy` is a single pass: dirty bytes in, a cleansed
payload plus a list of findings out. This module runs that pass repeatedly,
feeding each pass's cleansed payload back in as the next pass's input, until one
of these holds:

* **clean**   -- a pass returns zero findings; nothing left to do.
* **stable**  -- a pass returns findings but does not change a byte; those
  findings are things x12-tidy reports but cannot repair (e.g. a control-count
  mismatch), so further passes would be identical.
* **unrecoverable** -- a pass cannot find an ISA line at all (``payload is
  None``); there is nothing to iterate on.
* **max-iterations** -- the safety cap was hit first.

Why iterate at all, when one ``tidy`` call already reconstructs the envelope?
Because it keeps the *report* honest and legible: pass 1 shows the gross
structural repairs, pass 2 (on the now-canonical payload) shows only what
survives them, and the visitor can see the difference instead of one flat pile
of findings. In practice most inputs converge in one or two passes.

Everything in this module is pure: :func:`repair` reads nothing and writes
nothing, it just calls :func:`x12_tidy.tidy`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from x12_tidy import tidy

from x12_tidy_web.diagnostics import DiagnosticView, severity_counts, view_diagnostics

#: Default ceiling on passes. Real inputs converge in 1-2; this only bounds a
#: pathological oscillation that neither cleans nor stabilises.
DEFAULT_MAX_ITERATIONS = 5

#: Hard upper bound the API will accept, so a request cannot ask for a
#: thousand passes.
MAX_ALLOWED_ITERATIONS = 25

#: The byte<->text codec. Latin-1 is a total, round-tripping map between bytes
#: 0-255 and the first 256 code points, so any byte sequence survives a
#: ``.decode("latin-1").encode("latin-1")`` round trip unchanged. x12-tidy's own
#: docs recommend it for handling reconstructed payloads as text.
TEXT_CODEC = "latin-1"


def _to_text(data: bytes) -> str:
    return data.decode(TEXT_CODEC, errors="replace")


@dataclass(frozen=True)
class EnvelopeFactsView:
    """The plain envelope facts x12-tidy pulled from a payload, as strings.

    Mirrors :class:`x12_tidy.EnvelopeFacts`, decoded and stripped for display.
    ``None`` whenever the pass produced no payload.
    """

    sender_qualifier: str
    sender_id: str
    receiver_qualifier: str
    receiver_id: str
    usage_indicator: str
    interchange_date: str
    interchange_time: str
    interchange_version: str
    group_versions: list[str]
    functional_group_count: int
    transaction_set_count: int
    segment_count: int

    @classmethod
    def from_facts(cls, facts: Any | None) -> EnvelopeFactsView | None:
        if facts is None:
            return None

        def s(value: Any) -> str:
            if isinstance(value, (bytes, bytearray)):
                return bytes(value).decode(TEXT_CODEC, errors="replace").strip()
            return str(value)

        return cls(
            sender_qualifier=s(facts.sender_qualifier),
            sender_id=s(facts.sender_id),
            receiver_qualifier=s(facts.receiver_qualifier),
            receiver_id=s(facts.receiver_id),
            usage_indicator=s(facts.usage_indicator),
            interchange_date=s(facts.interchange_date),
            interchange_time=s(facts.interchange_time),
            interchange_version=s(facts.interchange_version),
            group_versions=[s(v) for v in getattr(facts, "group_versions", ()) or ()],
            functional_group_count=int(facts.functional_group_count),
            transaction_set_count=int(facts.transaction_set_count),
            segment_count=int(facts.segment_count),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "sender_qualifier": self.sender_qualifier,
            "sender_id": self.sender_id,
            "receiver_qualifier": self.receiver_qualifier,
            "receiver_id": self.receiver_id,
            "usage_indicator": self.usage_indicator,
            "interchange_date": self.interchange_date,
            "interchange_time": self.interchange_time,
            "interchange_version": self.interchange_version,
            "group_versions": list(self.group_versions),
            "functional_group_count": self.functional_group_count,
            "transaction_set_count": self.transaction_set_count,
            "segment_count": self.segment_count,
        }


@dataclass(frozen=True)
class Iteration:
    """One pass of :func:`x12_tidy.tidy`."""

    index: int  # 1-based
    input_text: str
    output_text: str | None  # None iff this pass could not recover a payload
    input_byte_length: int
    output_byte_length: int | None
    diagnostics: list[DiagnosticView]
    was_clean: bool
    changed: bool  # output differs from this pass's input
    facts: EnvelopeFactsView | None

    @property
    def severity_counts(self) -> dict[str, int]:
        return severity_counts(self.diagnostics)

    @property
    def shown(self) -> bool:
        """Whether this pass carries anything worth its own card in a
        rendered report. Pass 1 always does -- it is the only evidence for
        whether the input needed anything at all. A later pass that changed
        no byte and found nothing is proof the previous pass already reached
        the fixed point, not a fresh fact -- the run's ``verdict`` and pass
        count already say so once, so repeating an empty card adds nothing.
        ``iterations`` itself is never filtered -- this only tells a renderer
        which entries to skip."""
        return self.index == 1 or self.changed or bool(self.diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "input_byte_length": self.input_byte_length,
            "output_byte_length": self.output_byte_length,
            "was_clean": self.was_clean,
            "changed": self.changed,
            "shown": self.shown,
            "severity_counts": self.severity_counts,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
            "facts": self.facts.as_dict() if self.facts else None,
        }


#: The four ways :func:`repair` can stop. The value is a plain-language
#: explanation shown to the visitor wherever a run is summarised (the report,
#: the verdict sub-line, the demo) -- never show the bare key.
STOP_REASONS: dict[str, str] = {
    "clean": "the last pass came back with nothing left to flag.",
    "stable": (
        "the repair settled — running it again would change nothing, and the findings that "
        "remain are ones x12-tidy reports but does not attempt to fix."
    ),
    "unrecoverable": "no ISA header could be found, so there was no interchange to repair.",
    "max-iterations": (
        "it hit the pass limit before the result stopped changing — treat the output with care."
    ),
}


@dataclass(frozen=True)
class RepairRun:
    """The whole iterative run: every pass, plus the final verdict."""

    original_text: str
    final_text: str | None  # None iff the input was unrecoverable
    iterations: list[Iteration] = field(default_factory=list)
    stop_reason: str = "max-iterations"
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    codec: str = TEXT_CODEC

    @property
    def converged(self) -> bool:
        return self.stop_reason in ("clean", "stable")

    @property
    def recovered(self) -> bool:
        return self.final_text is not None

    @property
    def clean(self) -> bool:
        """True when the final payload has no findings at all."""
        return self.stop_reason == "clean" or (
            bool(self.iterations) and self.iterations[-1].was_clean
        )

    @property
    def changed(self) -> bool:
        """True when the corrected string differs from what was submitted."""
        return self.final_text is not None and self.final_text != self.original_text

    @property
    def residual_diagnostics(self) -> list[DiagnosticView]:
        """Findings from the final pass -- what x12-tidy still flags after repair."""
        return list(self.iterations[-1].diagnostics) if self.iterations else []

    @property
    def shown_iterations(self) -> list[Iteration]:
        """:attr:`iterations` filtered to the ones worth their own card --
        see :attr:`Iteration.shown`. Every renderer that lists passes reads
        this, not ``iterations`` directly, so the rule lives in one place."""
        return [it for it in self.iterations if it.shown]

    @property
    def all_diagnostics(self) -> list[DiagnosticView]:
        """Every finding from every pass, in pass order."""
        out: list[DiagnosticView] = []
        for it in self.iterations:
            out.extend(it.diagnostics)
        return out

    @property
    def final_facts(self) -> EnvelopeFactsView | None:
        for it in reversed(self.iterations):
            if it.facts is not None:
                return it.facts
        return None

    @property
    def residual_severity_counts(self) -> dict[str, int]:
        return severity_counts(self.residual_diagnostics)

    @property
    def stop_reason_detail(self) -> str:
        """Plain-language explanation of why the loop stopped (never the bare key)."""
        return STOP_REASONS.get(self.stop_reason, "")

    @property
    def verdict(self) -> dict[str, str]:
        """The single source of truth for the top-line result.

        Returns a stable ``state`` key, the ``css_class`` the web and demo
        panels style on, the ``headline`` sentence, and how to label the
        payload x12-tidy produced -- ``output_label`` (a section heading /
        panel title) and ``output_caveat`` (a warning line, or ``""``). Every
        renderer -- the live app (``static/app.js``), the downloaded report
        (``reporting.py``), and the static demo (``demo.py``) -- reads this and
        nothing else.

        The rule defined here once: **any residual fatal finding means the
        interchange cannot be repaired.** A fatal finding is one a conforming
        parser rejects outright; x12-tidy reports it but, by design, will not
        fabricate or guess the fix. So a run that ends with even one fatal
        residual is not a "corrected interchange" no matter how much structural
        cleanup earlier passes did -- it is a *partial repair that is still not
        conformant*, and both the label and the caveat say so.
        """
        counts = self.residual_severity_counts
        if not self.recovered:
            return {
                "state": "unrecoverable",
                "css_class": "fail",
                "headline": (
                    "Unrecoverable — no ISA line could be located, so there was nothing to repair."
                ),
                "output_label": "No output",
                "output_caveat": "",
            }
        if self.clean:
            return {
                "state": "clean",
                "css_class": "ok",
                "headline": "Clean — the interchange is conformant, with nothing left to fix.",
                "output_label": "Corrected interchange",
                "output_caveat": "",
            }
        if counts["fatal"]:
            n = counts["fatal"]
            noun = "finding" if n == 1 else "findings"
            them = "it" if n == 1 else "them"
            remains = "remains" if n == 1 else "remain"
            return {
                "state": "unfixable",
                "css_class": "fail",
                "headline": (
                    f"Cannot be repaired — {n} fatal {noun} below. A conforming parser rejects "
                    "an interchange that carries any fatal finding, and x12-tidy cannot fix "
                    f"{them} automatically. The structural repairs earlier passes made are still "
                    "shown below, but the result is not a conformant interchange."
                ),
                "output_label": "Partially repaired interchange — not conformant",
                "output_caveat": (
                    f"This still carries {n} fatal {noun} that a conforming parser will reject. "
                    f"We recommend reviewing this file and fixing {them} before sending it — a "
                    f"receiver's system will most likely be unable to read the interchange while "
                    f"{them} {remains}. It is not a drop-in replacement — resolve {them} in your "
                    "source data and repair again."
                ),
            }
        if not self.converged:
            return {
                "state": "notconverged",
                "css_class": "fail",
                "headline": (
                    "Did not converge within the pass limit — treat this output with care."
                ),
                "output_label": "Best-effort output — did not converge",
                "output_caveat": (
                    "The repair loop hit its pass limit without settling. Check this against the "
                    "passes above before relying on it."
                ),
            }
        if counts["error"]:
            n = counts["error"]
            noun = "finding" if n == 1 else "findings"
            return {
                "state": "residual-error",
                "css_class": "residual",
                "headline": (
                    f"Partly repaired — {n} conformance {noun} below could not be auto-repaired. "
                    "None are fatal, so a conforming parser will not reject the interchange outright."
                ),
                "output_label": "Repaired interchange — residual findings",
                "output_caveat": (
                    f"{n} conformance {noun} could not be auto-repaired (none fatal). Review the "
                    "passes above."
                ),
            }
        return {
            "state": "residual-advisory",
            "css_class": "residual",
            "headline": (
                "Repaired — no conformance errors remain. The findings below are advisory: trust "
                "and QA signals x12-tidy reports but does not change."
            ),
            "output_label": "Repaired interchange",
            "output_caveat": "",
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "x12-tidy-web/repair-run/1",
            "converged": self.converged,
            "recovered": self.recovered,
            "clean": self.clean,
            "changed": self.changed,
            "stop_reason": self.stop_reason,
            "stop_reason_detail": self.stop_reason_detail,
            "verdict": self.verdict,
            "max_iterations": self.max_iterations,
            "codec": self.codec,
            "iteration_count": len(self.iterations),
            "original_text": self.original_text,
            "final_text": self.final_text,
            "residual_severity_counts": self.residual_severity_counts,
            "final_facts": self.final_facts.as_dict() if self.final_facts else None,
            "iterations": [it.as_dict() for it in self.iterations],
        }


def _coerce_source(source: str | bytes) -> tuple[str, bytes]:
    if isinstance(source, str):
        return source, source.encode(TEXT_CODEC, errors="replace")
    data = bytes(source)
    return _to_text(data), data


def repair(
    source: str | bytes,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> RepairRun:
    """Run :func:`x12_tidy.tidy` to a fixed point.

    Args:
        source: the interchange, as text (encoded to bytes with latin-1) or raw
            bytes.
        max_iterations: safety cap on passes; clamped to
            ``1 .. MAX_ALLOWED_ITERATIONS``.

    Returns:
        A :class:`RepairRun` with one :class:`Iteration` per pass performed.
    """
    max_iterations = max(1, min(int(max_iterations), MAX_ALLOWED_ITERATIONS))
    original_text, current = _coerce_source(source)

    iterations: list[Iteration] = []
    final_bytes: bytes | None = current
    stop_reason = "max-iterations"

    for index in range(1, max_iterations + 1):
        result = tidy(current)
        payload: bytes | None = result.payload
        changed = payload is not None and payload != current

        iterations.append(
            Iteration(
                index=index,
                input_text=_to_text(current),
                output_text=None if payload is None else _to_text(payload),
                input_byte_length=len(current),
                output_byte_length=None if payload is None else len(payload),
                diagnostics=view_diagnostics(list(result.diagnostics)),
                was_clean=bool(result.was_clean),
                changed=changed,
                facts=EnvelopeFactsView.from_facts(result.facts),
            )
        )

        if payload is None:
            final_bytes = None
            stop_reason = "unrecoverable"
            break

        final_bytes = payload

        if result.was_clean:
            stop_reason = "clean"
            break
        if not changed:
            stop_reason = "stable"
            break

        current = payload

    return RepairRun(
        original_text=original_text,
        final_text=None if final_bytes is None else _to_text(final_bytes),
        iterations=iterations,
        stop_reason=stop_reason,
        max_iterations=max_iterations,
    )

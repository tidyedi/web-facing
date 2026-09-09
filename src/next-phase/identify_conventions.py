"""Issue #79 — per sample: cleanse, state the standard, list every segment.

Next-phase groundwork. NOT part of the shipped ``x12-tidy-web`` package (see this
directory's ``README.md``). Run directly:

    uv run python src/next-phase/identify_conventions.py

For every interchange in the app's sample corpus it:

1. **cleanses** it — the same iterative repair the app runs
   (:func:`x12_tidy_web.engine.repair`);
2. **states the standard** in the shape the project uses —
   ``sender-receiver-edinumber-edialpha-datesent``:

   =============  ====================================================
   sender         ISA06, the interchange sender id
   receiver       ISA08, the interchange receiver id
   edinumber      ST01, the transaction-set identifier code (e.g. 850)
   edialpha       the version letter from the GS08 implementation-
                  convention suffix (``A`` in ``004010X098A1``); ``-``
                  when GS08 carries no convention suffix
   datesent       ISA09, the interchange date (YYMMDD)
   =============  ====================================================

3. **lists every segment** — the full sequence in document order, no
   truncation, plus a per-identifier count;
4. emits the **segment reference-table keys** the next-phase parser will need.

Writes ``sample_conventions.md`` (readable) and ``sample_conventions.json``
(machine-readable) next to this file.

Why the segment list matters (next-phase intent)
------------------------------------------------
It becomes the **segment reference check**: before the translation step parses
an interchange, it must confirm a reference table exists for every segment the
interchange uses. Those tables are keyed
``sender-receiver-release_version-segment_abbrev`` (e.g.
``NORTHWIND-CONTOSO-004010-BEG``) — one per trading-partner pair, X12 release,
and segment, because a partner's implementation guide can define the same
segment differently. ``release_version`` here is the six-digit GS08 base
(``004010``). This key shape will grow as the design firms up.

Open design note: the envelope segments (ISA/GS/ST/SE/GE/IEA) are X12-standard
and do not vary by partner, so they may end up resolved from a shared table
rather than a per-partner one. This script currently emits a key for *every*
segment, envelope included, per the stated rule — revisit when the table
scheme is settled.

Note on the truncated sample: ``truncated-transmission`` is a deliberately
cut-off interchange. Its segment list ends where the bytes end (no SE/GE/IEA) —
that is the real content, not a display limit.

Performance: five short interchanges, well under a second. At thousands of files
the repair loop dominates — parallelise across files, not within one.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from x12_tidy_web.engine import repair
from x12_tidy_web.samples import SAMPLES

OUT_DIR = Path(__file__).parent

#: ST01 (Transaction Set Identifier Code) -> human name. Partial by design — the
#: ones in the sample corpus plus common neighbours. Extend as the corpus grows;
#: the authoritative list is X12 data element 143.
TRANSACTION_SET_NAMES: dict[str, str] = {
    "810": "Invoice",
    "820": "Payment Order / Remittance Advice",
    "830": "Planning Schedule with Release Capability",
    "837": "Health Care Claim",
    "846": "Inventory Inquiry / Advice",
    "850": "Purchase Order",
    "855": "Purchase Order Acknowledgement",
    "856": "Ship Notice / Manifest (ASN)",
    "860": "Purchase Order Change Request",
    "861": "Receiving Advice / Acceptance Certificate",
    "864": "Text Message",
    "940": "Warehouse Shipping Order",
    "943": "Warehouse Stock Transfer Shipment Advice",
    "944": "Warehouse Stock Transfer Receipt Advice",
    "945": "Warehouse Shipping Advice",
    "947": "Warehouse Inventory Adjustment Advice",
    "997": "Functional Acknowledgement",
    "999": "Implementation Acknowledgement",
}

#: A well-formed GS08: six base digits (version + release + subrelease) then an
#: optional implementation-convention reference, e.g. ``004010X098A1`` -> base
#: ``004010``, convention ``X098A1``.
_GS08_RE = re.compile(r"^(?P<base>\d{6})(?P<convention>[A-Z0-9]+)?$")

#: In a convention suffix like ``X098A1`` the "version letter" is the ``A`` that
#: sits before any trailing digits.
_EDIALPHA_RE = re.compile(r"([A-Z])\d*$")


@dataclass(frozen=True)
class StandardId:
    """The interchange's standard as ``sender-receiver-edinumber-edialpha-datesent``."""

    sender: str  # ISA06
    receiver: str  # ISA08
    edi_number: str  # ST01
    edi_alpha: str  # GS08 convention version letter, or "-"
    date_sent: str  # ISA09 (YYMMDD)

    def as_label(self) -> str:
        return "-".join(
            [
                self.sender or "?",
                self.receiver or "?",
                self.edi_number or "?",
                self.edi_alpha or "-",
                self.date_sent or "?",
            ]
        )


@dataclass(frozen=True)
class SegmentUse:
    identifier: str
    count: int


@dataclass
class SampleAnalysis:
    slug: str
    title: str
    verdict_state: str
    standard: StandardId
    standard_label: str
    transaction_set_name: str | None
    interchange_version: str  # ISA12
    group_versions: list[str]  # GS08(s)
    release_version: str  # six-digit GS08 base, e.g. "004010"
    implementation_convention: str | None  # full GS08 suffix, e.g. "X098A1"
    segment_sequence: list[str] = field(default_factory=list)  # every segment, in order
    segment_counts: list[SegmentUse] = field(default_factory=list)  # per identifier
    segment_total: int = 0
    # sender-receiver-release_version-segment_abbrev, one per distinct segment
    segment_reference_keys: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _delimiters(final_text: str) -> tuple[str, str]:
    """(element separator, segment terminator) from the canonical ISA line.

    After repair the interchange starts with a 106-character ISA segment: byte 3
    is the element separator, byte 105 the segment terminator. Falls back to
    ``*`` / ``~`` if the text somehow does not start with ``ISA``.
    """
    if final_text[:3] == "ISA" and len(final_text) >= 106:
        return final_text[3], final_text[105]
    return "*", "~"


def _segments(final_text: str) -> list[str]:
    """Every segment identifier, in document order, nothing dropped."""
    element_sep, terminator = _delimiters(final_text)
    out: list[str] = []
    for raw in final_text.split(terminator):
        seg = raw.strip()
        if not seg:
            continue
        identifier = seg.split(element_sep, 1)[0].strip().upper()
        if identifier:
            out.append(identifier)
    return out


def _element(final_text: str, segment_id: str, index: int) -> str | None:
    """The ``index``-th element (1-based) of the first ``segment_id`` segment."""
    element_sep, terminator = _delimiters(final_text)
    for raw in final_text.split(terminator):
        seg = raw.strip()
        if seg.split(element_sep, 1)[0].strip().upper() == segment_id:
            parts = seg.split(element_sep)
            if len(parts) > index and parts[index].strip():
                return parts[index].strip()
            return None
    return None


def _edialpha(gs08: str | None) -> tuple[str, str | None]:
    """(edialpha, full convention suffix). ``("-", None)`` when GS08 is bare."""
    if not gs08:
        return "-", None
    m = _GS08_RE.match(gs08)
    suffix = m.group("convention") if m else None
    if not suffix:
        return "-", None
    letter = _EDIALPHA_RE.search(suffix)
    return (letter.group(1) if letter else "-"), suffix


def analyze(slug: str, title: str, edi: str) -> SampleAnalysis:
    run = repair(edi.encode("latin-1"))
    data = run.as_dict()
    facts = data["final_facts"] or {}
    final_text: str = data["final_text"] or ""

    interchange_version = str(facts.get("interchange_version", "")).strip()
    group_versions = [str(v).strip() for v in facts.get("group_versions", [])]
    gs08 = group_versions[0] if group_versions else None

    st01 = _element(final_text, "ST", 1) or ""
    edi_alpha, convention = _edialpha(gs08)

    standard = StandardId(
        sender=str(facts.get("sender_id", "")).strip(),
        receiver=str(facts.get("receiver_id", "")).strip(),
        edi_number=st01,
        edi_alpha=edi_alpha,
        date_sent=str(facts.get("interchange_date", "")).strip(),
    )

    sequence = _segments(final_text)
    counts = Counter(sequence)
    ordered_ids: list[str] = list(dict.fromkeys(sequence))

    release_version = (group_versions[0][:6] if group_versions else "")
    sender = str(facts.get("sender_id", "")).strip()
    receiver = str(facts.get("receiver_id", "")).strip()
    ref_prefix = f"{sender or '?'}-{receiver or '?'}-{release_version or '?'}"

    analysis = SampleAnalysis(
        slug=slug,
        title=title,
        verdict_state=str(data["verdict"]["state"]),
        standard=standard,
        standard_label=standard.as_label(),
        transaction_set_name=TRANSACTION_SET_NAMES.get(st01),
        interchange_version=interchange_version,
        group_versions=group_versions,
        release_version=release_version,
        implementation_convention=convention,
        segment_sequence=sequence,
        segment_counts=[SegmentUse(identifier=i, count=counts[i]) for i in ordered_ids],
        segment_total=len(sequence),
        segment_reference_keys=[f"{ref_prefix}-{seg}" for seg in ordered_ids],
    )

    if st01 and analysis.transaction_set_name is None:
        analysis.notes.append(f"ST01 {st01!r} not in the local transaction-set name table.")
    if convention is None:
        analysis.notes.append(
            "GS08 carries no implementation-convention reference (bare version); "
            "edialpha is '-'. Which guide applies is a trading-partner agreement."
        )
    if not release_version:
        analysis.notes.append(
            "No GS08 to take a release_version from — segment reference-table keys "
            "fall back to '?' for that field."
        )
    if "SE" not in counts or "IEA" not in counts:
        analysis.notes.append(
            "Interchange has no SE/GE/IEA trailer — it is genuinely cut off; "
            "the segment list ends where the bytes end."
        )
    if data["verdict"]["state"] not in {"clean", "residual-advisory"}:
        analysis.notes.append(
            f"Repair verdict is '{analysis.verdict_state}'; the segment list is of "
            "the best-effort repair."
        )
    return analysis


def render_markdown(results: list[SampleAnalysis]) -> str:
    lines: list[str] = [
        "# Sample interchanges — standard and full segment list",
        "",
        (
            "Generated by `src/next-phase/identify_conventions.py` (issue #79). "
            "Not a shipped feature."
        ),
        "",
        (
            "Standard shape: `sender-receiver-edinumber-edialpha-datesent` "
            "(ISA06-ISA08-ST01-GS08 convention letter-ISA09)."
        ),
        "",
        (
            "Segment reference-table key shape: "
            "`sender-receiver-release_version-segment_abbrev` — the next-phase "
            "parser checks one exists for every segment before translating."
        ),
        "",
    ]
    for r in results:
        lines += [
            f"## {r.title}",
            "",
            f"- **standard:** `{r.standard_label}`",
            f"- **slug:** `{r.slug}`",
            f"- **repair verdict:** {r.verdict_state}",
            f"- **transaction set:** {r.standard.edi_number or '—'}"
            + (f" — {r.transaction_set_name}" if r.transaction_set_name else ""),
            f"- **interchange version (ISA12):** {r.interchange_version or '—'}",
            f"- **group version (GS08):** {', '.join(r.group_versions) or '—'}",
            f"- **implementation convention:** {r.implementation_convention or 'none (bare version)'}",
            f"- **segment count:** {r.segment_total}",
            "",
            "Full segment sequence (document order):",
            "",
            "```",
            " ".join(r.segment_sequence) if r.segment_sequence else "(none)",
            "```",
            "",
            "| # | segment | count |",
            "|--:|:--|--:|",
        ]
        for i, seg in enumerate(r.segment_counts, 1):
            lines.append(f"| {i} | `{seg.identifier}` | {seg.count} |")
        lines += [
            "",
            "Segment reference-table keys needed to parse this interchange:",
            "",
            "```",
            *r.segment_reference_keys,
            "```",
            "",
        ]
        if r.notes:
            lines.append("Notes:")
            lines += [f"- {n}" for n in r.notes]
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    results = [analyze(s.slug, s.title, s.edi) for s in SAMPLES]

    md_path = OUT_DIR / "sample_conventions.md"
    json_path = OUT_DIR / "sample_conventions.json"
    md_path.write_text(render_markdown(results), encoding="utf-8")
    json_path.write_text(
        json.dumps([asdict(r) for r in results], indent=2) + "\n", encoding="utf-8"
    )

    for r in results:
        print(f"{r.slug:24} {r.standard_label}")
        print(f"{'':24} {r.segment_total} segments: {' '.join(r.segment_sequence)}")
        print(f"{'':24} ref keys: {', '.join(r.segment_reference_keys)}")
    print(f"\nwrote {md_path.relative_to(Path.cwd())}")
    print(f"wrote {json_path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()

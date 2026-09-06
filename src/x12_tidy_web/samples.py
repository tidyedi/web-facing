# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""The broken interchanges the form and the static demo pages draw from.

Three of them, each with a distinct repair story so the demo pages (issue #32)
show different behaviour:

* ``forwarded-email`` — junk before the ISA, trimmed ISA elements, and a bad
  functional-group count. Ends *stable* with one residual fatal x12-tidy can
  flag but not guess a fix for.
* ``pipe-delimited`` — a pipe-delimited, newline-terminated ASN with short ISA
  elements. x12-tidy parses the non-standard delimiters and pads the elements;
  ends *clean*.
* ``lowercased-isa`` — a functional acknowledgement whose ``ISA`` tag arrived
  lowercase. One error, uppercased; ends *clean*.

Kept here rather than in the repo-root ``samples/`` directory so they ship in
the wheel and the Docker image. The ``samples/*.edi`` files are generated copies
for shell use — regenerate with ``python -m x12_tidy_web.samples``.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sample:
    """One demo interchange."""

    slug: str
    title: str
    blurb: str  # one sentence, shown under the form and on the demo page
    edi: str


SAMPLES: tuple[Sample, ...] = (
    Sample(
        slug="forwarded-email",
        title="Forwarded email — 850 purchase order",
        blurb=(
            "A purchase order pasted straight out of a forwarded email: an "
            "email header sits before the ISA, four ISA elements were trimmed "
            "below their fixed width, and IEA01 claims two functional groups "
            "when there is one."
        ),
        edi=(
            "Subject: FW: Q1 reorder - please confirm\r\n"
            "From: purchasing@northwind-traders.example\r\n\r\n"
            "ISA*00*   *00*   *ZZ*NORTHWIND*ZZ*CONTOSO*240401*0915*U*00401*000000501*0*P*:~"
            "GS*PO*NORTHWIND*CONTOSO*20240401*0915*501*X*004010~"
            "ST*850*0001~"
            "BEG*00*NE*PO-2024-0501**20240401~"
            "N1*ST*Northwind Traders Warehouse 3~"
            "PO1*1*24*CA*18.50**BP*NW-COFFEE-005~"
            "PO1*2*6*EA*42.00**BP*NW-GRINDER-XL~"
            "CTT*2~"
            "SE*7*0001~"
            "GE*1*501~"
            "IEA*2*000000501~"
        ),
    ),
    Sample(
        slug="pipe-delimited",
        title="Pipe-delimited — 856 advance ship notice",
        blurb=(
            "An ASN that uses '|' as the element separator and a newline as the "
            "segment terminator, with several ISA elements shorter than their "
            "fixed width. x12-tidy reads the non-standard delimiters and pads "
            "the elements; the result is conformant."
        ),
        edi=(
            "ISA|00|   |00|   |ZZ|FASTSHIP|ZZ|MEGABUY|240515|1830|U|00401|000000777|0|P|>\n"
            "GS|SH|FASTSHIP|MEGABUY|20240515|1830|777|X|004010\n"
            "ST|856|0001\n"
            "BSN|00|SHIP-77801|20240515|1830\n"
            "HL|1||S\n"
            "TD1|CTN25|4\n"
            "REF|BM|BOL-99823\n"
            "HL|2|1|O\n"
            "PRF|PO-2024-0501\n"
            "HL|3|2|I\n"
            "LIN|1|BP|NW-COFFEE-005\n"
            "SN1|1|24|CA\n"
            "SE|11|0001\n"
            "GE|1|777\n"
            "IEA|1|000000777\n"
        ),
    ),
    Sample(
        slug="lowercased-isa",
        title="Lowercased tag — 997 functional acknowledgement",
        blurb=(
            "A functional acknowledgement whose ISA segment tag arrived in "
            "lowercase ('isa'). x12-tidy uppercases it; nothing else is wrong "
            "and the result is conformant."
        ),
        edi=(
            "isa*00*          *00*          *ZZ*GATEWAYEDI     *ZZ*PARTNERX"
            "       *240102*0801*U*00401*000000015*0*P*:~"
            "GS*FA*GATEWAYEDI*PARTNERX*20240102*0801*15*X*004010~"
            "ST*997*0001~"
            "AK1*PO*501~"
            "AK2*850*0001~"
            "AK5*A~"
            "AK9*A*1*1*1~"
            "SE*6*0001~"
            "GE*1*15~"
            "IEA*1*000000015~"
        ),
    ),
)

_BY_SLUG = {s.slug: s for s in SAMPLES}


def by_slug(slug: str) -> Sample:
    """Look up a sample, or raise ``KeyError``."""
    return _BY_SLUG[slug]


def random_sample(exclude: str | None = None) -> Sample:
    """A sample chosen at random, optionally not the one whose slug is ``exclude``."""
    pool = [s for s in SAMPLES if s.slug != exclude] or list(SAMPLES)
    return random.choice(pool)


def _write_edi_files(target: Path) -> None:
    """(Re)generate ``samples/<slug>.edi`` from :data:`SAMPLES`."""
    target.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        path = target / f"{sample.slug}.edi"
        path.write_text(sample.edi, encoding="latin-1")
        print(f"wrote {path}")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "samples"
    _write_edi_files(root)

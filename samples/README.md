# Sample interchanges

Broken fixtures for exercising x12-tidy-web end to end. These are *our* files —
x12-tidy ships its own real-world samples in its repo.

**Source of truth: [`src/x12_tidy_web/samples.py`](../src/x12_tidy_web/samples.py).**
The `.edi` files here are generated from it (`python -m x12_tidy_web.samples`);
the form's "Load a random sample" button and the static demo pages
(`x12-tidy-web demo`) use the same five.

Run one from the shell:

```bash
uv run x12-tidy-web repair samples/forwarded-email.edi
```

Or paste its contents into the form.

| File | What's wrong | Outcome |
| --- | --- | --- |
| `forwarded-email.edi` | Email header before the ISA, four ISA elements trimmed below their fixed width, IEA01 claiming two functional groups when there is one. | **Stable** — repaired, but the group-count mismatch is a trust signal x12-tidy flags and cannot fix. |
| `pipe-delimited.edi` | `\|`-delimited, newline-terminated ASN with short ISA elements. | **Clean** — x12-tidy reads the non-standard delimiters and pads the elements. |
| `lowercased-isa.edi` | The `ISA` segment tag arrived lowercase (`isa`). | **Clean** — uppercased; nothing else was wrong. |
| `truncated-transmission.edi` | A claim file cut off mid-transaction: no SE, no GE, no IEA. | **Stable** — x12-tidy names every missing trailer (fatal) but changes nothing; it will not fabricate structure. |
| `wrapped-isa.edi` | A mail client put a CR/LF inside an ISA element. | **Clean** — the break becomes a space, the element is re-measured. |

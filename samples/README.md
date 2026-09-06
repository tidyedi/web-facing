# Sample interchanges

Hand-written fixtures for exercising x12-tidy-web end to end. These are *our*
files — x12-tidy ships its own real-world samples in its repo.

Run one from the shell:

```bash
uv run x12-tidy-web repair samples/broken-850-leading-bytes.edi
```

Or paste its contents into the form.

## `broken-850-leading-bytes.edi`

A minimal 850 (purchase order) interchange with three deliberate problems:

- **Leading bytes** — an email header precedes the `ISA` segment (a `warning`;
  stripped).
- **Short ISA elements** — `ISA06`/`ISA08` are 4 bytes, not their fixed width of
  15 (an `error`; space-padded).
- **Control-count mismatch** — `IEA01` claims 2 functional groups but there is
  one (a `fatal` trust signal; x12-tidy reports it but cannot know the right
  value, so it survives every repair pass — this is what a "stable" stop with
  residual findings looks like).

# `isa/`

Single-source ISA definition for JANUS.

- `isa.yaml` — instruction encodings, semantics, aliases, memory map and pin map

Generated outputs (do not edit by hand):

- `src/isa_pkg.sv` — opcodes, field positions, memory map and pin masks for RTL
- `docs/isa.md` — human-readable reference

Regenerate both with `python tools/gen_isa.py`. CI runs `--check` to catch drift.

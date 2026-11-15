# `isa/`

Single-source ISA definition for JANUS.

Planned contents:

- `isa.yaml` — instruction encodings, semantics, CSRs and the peripheral memory map
- Generated outputs (do not edit by hand):
  - `src/isa_pkg.sv`
  - `sw/include/janus/isa.hpp`
  - `docs/isa.md`

The generator lives in `tools/`.

# `sw/`

Host-side and build-time toolchain.

Planned contents:

- `asm/` — `jasm`, the C++20 assembler
- `iss/` — `jrun`, the cycle-accurate instruction-set simulator
- `cosim/` — `jcosim`, Verilator + ISS lockstep harness
- `lib/` — reusable assembly routines (UART, SPI, I2C, ...)
- `host/` — program loader for the RP2040 demo board

A short-lived Python prototype for ISA validation will live here during the first
milestone.

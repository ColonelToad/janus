# JANUS

A reprogrammable 32-bit protocol engine for the
[Jane Street protocol emulator ASIC competition](https://blog.janestreet.com/protocol-emulator-asic-competition/).

JANUS is a small custom processor designed for cycle-accurate pin timing. Instead of fixed
UART/SPI/I2C blocks, firmware drives the chip's 24 digital pins directly, so new protocols can
be added after fabrication.

> **Status:** project bootstrap. The top level is still a passthrough placeholder; the core,
> ISA, toolchain and tests are the next milestone.

## Target

| | |
|---|---|
| Process | IHP SG13CMOS5L via Tiny Tapeout |
| Area | 8x4 tiles (~1.0 mm²) |
| Clock | 50 MHz target (20 ns period) |
| I/O | 8 inputs, 8 outputs, 8 bidirectional |
| Top module | `tt_um_coloneltoad_janus` |
| License | Apache-2.0 |

## Planned architecture

- Custom 32-bit ISA, 16 registers, 512x32-bit instruction SRAM
- Two hardware contexts, barrel-interleaved, for concurrent protocols
- 32-bit cycle counter with timestamped `WAIT` / `WAITABS` / `WAITPIN` instructions
- Per-pin direction control, 2-FF synchronizers and edge detection
- Shift engines, CRC-16/CRC-32 assist, timers and interrupts
- UART bootloader on `uio[0:1]` for host-side program loading

Protocol targets: UART, SPI (modes 0-3), I2C (controller and target), PS/2, JTAG/SWD.
Stretch goals: low-speed USB and 10BASE-T.

See [docs/architecture.md](docs/architecture.md) for the working design notes.

## Repository layout

| Path | Contents |
|---|---|
| `src/` | SystemVerilog RTL (Tiny Tapeout entry point) |
| `test/` | cocotb smoke test and Tiny Tapeout test harness |
| `isa/` | Single-source ISA definition (planned) |
| `sw/` | C++ assembler, ISS and co-simulation (planned) |
| `sim/` | Formal, gate-level and protocol verification (planned) |
| `tools/` | Build-time code generation (planned) |
| `programs/` | Example protocol firmware (planned) |
| `docs/` | Architecture, ISA and verification documentation |

## Getting started

Prerequisites: Python 3.11+, `cocotb`, and a supported simulator (Icarus Verilog or
Verilator).

```sh
cd test
make                  # Icarus Verilog
make SIM=verilator    # Verilator
```

The RTL currently passes the dedicated inputs through to the outputs so the template harness
stays green.

## Continuous integration

The `test` workflow runs on every push. The `gds` and `docs` workflows are manual
(`workflow_dispatch`) so that hardening runs happen deliberately at milestones rather than
on every commit.

## Links

- [Competition announcement](https://blog.janestreet.com/protocol-emulator-asic-competition/)
- [Tiny Tapeout](https://tinytapeout.com/)
- [CMOS5L Verilog template](https://github.com/TinyTapeout/ttihp-verilog-template/tree/cmos5l)

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

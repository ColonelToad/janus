# JANUS

A reprogrammable 32-bit protocol engine for the
[Jane Street protocol emulator ASIC competition](https://blog.janestreet.com/protocol-emulator-asic-competition/).

JANUS is a small custom processor designed for cycle-accurate pin timing. Instead of fixed
UART/SPI/I2C blocks, firmware drives the chip's 24 digital pins directly, so new protocols can
be added after fabrication.

> **Status:** ISA v0.1, assembler and cycle-accurate ISS are in place and tested. The RTL
> top level is still a passthrough placeholder; the core is the next milestone.

## Target

| | |
|---|---|
| Process | IHP SG13CMOS5L via Tiny Tapeout |
| Area | 8x4 tiles (~1.0 mm²) |
| Clock | 50 MHz target (20 ns period) |
| I/O | 8 inputs, 8 outputs, 8 bidirectional |
| Top module | `tt_um_coloneltoad_janus` |
| License | Apache-2.0 |

## Architecture

- Custom 32-bit ISA, 16 registers, 512x32-bit instruction SRAM
- Two hardware contexts, barrel-interleaved, for concurrent protocols
- 32-bit cycle counter with `WAITREL`, `WAITABS` and `WAITPIN` instructions
- Per-pin direction control, 2-FF synchronizers and sticky edge detection
- UART bootloader on `uio[0:1]` for host-side program loading
- Protocols are bit-banged in firmware, so no fixed protocol blocks are needed

Protocol targets: UART, SPI (modes 0-3), I2C (controller and target), PS/2, JTAG/SWD.
Stretch goals: low-speed USB and 10BASE-T.

The ISA is defined once in [`isa/isa.yaml`](isa/isa.yaml) and drives the assembler, the ISS,
the RTL package and the reference documentation. See
[docs/architecture.md](docs/architecture.md) and [docs/isa.md](docs/isa.md).

## Toolchain

The assembler and instruction-set simulator are written in Python so they integrate
directly with cocotb and run anywhere. Usage, from the repository root:

```sh
export PYTHONPATH=sw
python -m janus asm programs/hello.s --hex
python -m janus run programs/hello.s
python -m janus run programs/two_contexts.s --entry1 ctx1 --cycles 200
python -m janus disasm hello.bin
```

Run the toolchain tests with `python -m pytest sw/tests`. Generated RTL constants and the
ISA reference are refreshed with `python tools/gen_isa.py`; CI checks that they are current.

## Repository layout

| Path | Contents |
|---|---|
| `src/` | SystemVerilog RTL (Tiny Tapeout entry point) |
| `test/` | cocotb smoke test and Tiny Tapeout test harness |
| `isa/` | Single-source ISA definition |
| `sw/` | Python assembler, ISS and toolchain tests |
| `sim/` | Formal, gate-level and protocol verification |
| `tools/` | Build-time code generation |
| `programs/` | Example firmware |
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
stays green. The toolchain tests do not need a simulator.

## Continuous integration

The `test` workflow runs on every push. The `gds` and `docs` workflows are manual
(`workflow_dispatch`) so that hardening runs happen deliberately at milestones rather than
on every commit.

## Links

- [Competition announcement](https://blog.janestreet.com/protocol-emulator-asic-competition/)
- [Tiny Tapeout](https://tinytapeout.com/)
- [Tiny Tapeout Verilog template](https://github.com/TinyTapeout/ttihp-verilog-template)

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

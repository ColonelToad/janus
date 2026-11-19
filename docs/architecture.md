# JANUS architecture

Status: ISA v0.1 and the host toolchain are implemented. The RTL core is in bring-up.

Target: 8x4 tiles (~1.0 mm²) on IHP SG13CMOS5L, using Tiny Tapeout's `ttihp27a` flow.

## Goals

1. **Reprogrammable after fabrication.** No fixed protocol blocks; protocols live in
   firmware.
2. **Cycle-accurate timing.** Firmware can place pin transitions on exact cycles.
3. **Concurrency.** Two protocol engines can run at once.
4. **Verifiable.** RTL, assembler and simulator share one ISA definition and a lockstep
   test harness.

## Block sketch

```
                 +---------------------------------------------+
  host UART ---->| bootloader FSM ---> instruction SRAM        |
                 |                                             |
  pins <-------->| GPIO / edge detect <--- core (2 contexts)   |
                 |        ^                    |               |
                 |        |                    v               |
                 |   cycle counter         data SRAM           |
                 +---------------------------------------------+
```

## Core

- 32-bit fixed-width instructions, 16 registers per context (`r0` is hardwired zero,
  `r15` is the conventional link register).
- Two hardware contexts. Context 0 issues on even cycles and context 1 on odd cycles. A
  stalled context keeps its slot idle rather than handing it to the other context, so the
  issue cycle of every instruction is predictable.
- Per-context state: PC, register file, wait state and deadline, halted flag.
- Shared state: ALU, decoder, instruction memory, data memory, pin registers, cycle
  counter.
- 512x32-bit instruction memory (2 KB), writable only by the bootloader.
- Data memory starts at 512x32 bits (2 KB); the final size follows the area report.
- No caches and no interrupts in the MVP. Polling and timed waits are enough for UART,
  SPI and I2C.

The first core will be a simple multi-cycle machine that issues at most one instruction
per context slot. This keeps the ISS model exact: one instruction per slot, memory access
in the same slot, and no pipeline hazards to model.

## Timing model

`CYCLE` is a free-running 32-bit counter at the core clock. It wraps about every 86
seconds at 50 MHz, which is far longer than any protocol transaction.

- `WAITREL rs` stalls the issuing context until `CYCLE >= issue_cycle + rs`.
- `WAITABS rs` stalls until `CYCLE >= rs`.
- `WAITPIN rs1, rs2` stalls until an edge appears on any pin selected by `rs1`, or until
  `CYCLE >= rs2` when `rs2` is non-zero. Edge flags are sticky and cleared by writing one
  to `PIN_EDGE`.

Because a context resumes on its next own slot, a wait of `n` cycles from an even slot
returns on the next even cycle at or after the deadline. Firmware examples and the ISS
account for this explicitly; the assembler does not hide it.

## I/O

24 pins:

- pins 0-7 are `ui_in[0:7]`, input only
- pins 8-15 are `uo_out[0:7]`, output only
- pins 16-23 are `uio[0:7]`, bidirectional

`PIN_OUT`, `PIN_DIR`, `PIN_SET`, `PIN_CLR` and `PIN_XOR` control the output level and
direction. `PIN_IN` returns the synchronized input levels. `PIN_EDGE` records a one-bit
sticky flag per input-capable pin whenever the synchronized value changes.

No shift engines or CRC assist in the MVP. Bit-banging at 25 MIPS per context is enough
for UART, SPI and I2C, and software keeps the RTL small and the write-up simple.

## Boot flow

On reset the core is held while a small hardware bootloader listens on `uio[0]` and
`uio[1]` at a fixed baud rate. The host sends a little-endian image introduced by the
magic value `0x4A414E5553` ("JANUS"). The image header carries the entry point for each
context and the code length; the bootloader writes the code into instruction memory,
checks the image and releases the core.

Firmware can write `0x4A4E5553` to `BOOT_REQ` to hand the pins back to the bootloader and
load a new image without resetting the chip. That is the reprogrammability demo.

The host is expected to be the Tiny Tapeout demo-board MCU, but the packet format is
documented so any host can load a program.

## Toolchain

- `isa/isa.yaml` — single source of truth for encodings, semantics, aliases, memory map
  and pin map.
- `tools/gen_isa.py` — generates `src/isa_pkg.sv` and `docs/isa.md`; CI verifies they are
  current.
- `sw/janus/assembler.py` — two-pass assembler with labels, expressions, directives and
  aliases.
- `sw/janus/iss.py` — cycle-accurate two-context ISS, used as the reference model for
  RTL/ISS lockstep.
- `sw/janus/__main__.py` — `asm`, `run`, `disasm` and `isa` commands.
- `programs/` — example firmware, starting with `hello.s` and `two_contexts.s`.

Python is used where iteration speed and cocotb integration dominate. C++ or Rust will
only be introduced if a specific tool needs the performance or an existing library makes
it the right choice.

## Verification strategy

1. **Toolchain tests** — assembler encodings, directives, error handling, ISS semantics,
   wait behaviour and context interleaving (`sw/tests`).
2. **RTL/ISS lockstep** — run the same firmware on the RTL and the ISS, compare
   architectural state and pin transitions every cycle.
3. **Constrained-random firmware** — generate valid instruction sequences and compare
   RTL and ISS over long runs.
4. **Protocol agents** — cocotb UART/SPI/I2C masters and slaves check the firmware against
   independent models.
5. **Gate-level simulation** — rerun the protocol tests on the hardened netlist.
6. **Tiny Tapeout precheck and GDS** — the sanctioned flow in GitHub Actions.

Formal properties are optional and not on the critical path.

## Open decisions

- Final data-memory size and whether it is flop-based or an SRAM macro.
- Bootloader baud rate and packet layout.
- Pin assignment conventions for each protocol demo.
- Clock target after timing closure (50 MHz baseline, 60 MHz only with margin).
- Second-context go/no-go after the first protocol demos work.

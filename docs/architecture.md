# JANUS architecture

Status: working draft for the bootstrap milestone. Details will change as the core is built.

Target: 8x4 tiles (~1.0 mm²) on IHP SG13CMOS5L, using Tiny Tapeout's `ttihp27a` flow.

## Goals

1. **Reprogrammable after fabrication.** No fixed protocol blocks; protocols live in firmware.
2. **Cycle-accurate timing.** Firmware can place pin transitions on exact cycles.
3. **Concurrency.** Multiple protocol engines can run at once.
4. **Verifiable.** RTL, assembler and simulator share one ISA definition and a lockstep test
   harness.

## Block sketch

```
                 +---------------------------------------------+
   host UART --->| bootloader FSM ---> instruction SRAM        |
                 |                                             |
   pins <------->| GPIO / edge detect <--- core (2 contexts)  |
                 |        ^                    |               |
                 |        |                    v               |
                 |  shift engines          data SRAM          |
                 |  CRC / timers / IRQ                         |
                 +---------------------------------------------+
```

## Core

- 32-bit fixed-width instructions, 16 registers (`r0` hardwired to zero)
- Two hardware contexts, barrel-interleaved, each with private PC, registers, pin masks and
  a deadline register
- 512x32-bit instruction SRAM, 256x32-bit data SRAM
- Global free-running 32-bit cycle counter
- Timestamped waits: `WAIT` (relative), `WAITABS` (absolute cycle), `WAITPIN` (edge with
  timeout)

## I/O and assist

- 24 digital pins: 8 dedicated inputs, 8 dedicated outputs, 8 bidirectional
- Per-pin direction and output control; 2-FF input synchronizers; edge detection
- Configurable TX/RX shift engines for UART/SPI-style traffic
- CRC-16 and CRC-32 LFSRs for USB/Ethernet work
- Timers and an interrupt controller

## Boot flow

On reset, a small hardware bootloader listens on `uio[0:1]` (UART), receives a program image
into instruction SRAM, verifies it and jumps to the entry point. Firmware can then remap the
pins for the protocol under test. The host is expected to be the demo board MCU, but the
protocol will be documented so any host can load a program.

## Open decisions

- Final ISA encoding and instruction list
- Memory sizes after the first synthesis area report
- Whether the data memory should be a separate SRAM macro or flop-based
- Pin assignment for the boot UART and protocol demos
- Clock target after timing closure (50 MHz desired, 25 MHz fallback)

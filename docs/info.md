<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

# JANUS: Programmable Protocol Emulator

A reprogrammable 32-bit protocol engine for UART, SPI, I2C and beyond, designed for the
[Jane Street protocol emulator ASIC competition](https://blog.janestreet.com/protocol-emulator-asic-competition/).

## How it works

JANUS is a small custom processor built for cycle-accurate pin timing. Firmware drives the
24 digital I/O pins directly, so new protocols can be added after fabrication instead of
being baked into fixed UART/SPI/I2C blocks.

Planned architecture:

- 32-bit custom ISA, 16 registers, 512x32-bit instruction SRAM
- Two hardware contexts for concurrent protocol engines
- Global cycle counter with timestamped wait instructions
- Per-pin direction control, edge detection, shift engines and CRC assist
- UART bootloader so a host MCU can load programs after reset

See [architecture.md](architecture.md) for details. The design is in early bring-up; this
datasheet will be updated as the core and toolchain land.

## How to test

Run the cocotb smoke test:

```sh
cd test
make
```

Programs will be assembled with `jasm` and run on the `jrun` instruction-set simulator once
the toolchain lands.

## External hardware

None required for the core design. The final protocol demos may use the Tiny Tapeout ETR
demo board and a Pmod for level shifting or pull-ups.

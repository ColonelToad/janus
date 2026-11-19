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

- 32-bit custom ISA, 16 registers per context, 512x32-bit instruction memory
- Two hardware contexts issued on alternating cycles for concurrent protocol engines
- Global 32-bit cycle counter with `WAITREL`, `WAITABS` and `WAITPIN` instructions
- Per-pin direction control and sticky edge detection
- UART bootloader so a host MCU can load programs after reset

The ISA is defined once in [`isa/isa.yaml`](../isa/isa.yaml) and drives the assembler, the
instruction-set simulator, the RTL constants and the [ISA reference](isa.md). See
[architecture.md](architecture.md) for the design and timing model.

## How to test

Run the cocotb smoke test:

```sh
cd test
make
```

Run the assembler and ISS tests:

```sh
pip install -r sw/requirements.txt
python -m pytest sw/tests
```

Assemble and run an example:

```sh
export PYTHONPATH=sw
python -m janus run programs/hello.s
python -m janus run programs/two_contexts.s --entry1 ctx1 --cycles 200
```

## External hardware

None required for the core design. The protocol demos use the Tiny Tapeout demo board; I2C
demos may use a Pmod for pull-ups.

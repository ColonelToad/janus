# `sw/`

Host-side toolchain.

- `janus/isa.py` — loads `isa/isa.yaml` and exposes instruction/format tables
- `janus/assembler.py` — two-pass assembler with labels, expressions, directives and aliases
- `janus/iss.py` — cycle-accurate two-context instruction-set simulator
- `janus/__main__.py` — `asm`, `run`, `disasm` and `isa` commands
- `tests/` — pytest suites for the ISA, assembler and ISS

The Python implementation is the reference toolchain. It integrates directly with cocotb
and keeps the feedback loop short. A C++ or Rust component will only be added where a
concrete need (speed or an existing library) justifies it.

Usage from the repository root:

```sh
pip install -r sw/requirements.txt
export PYTHONPATH=sw
python -m janus run programs/hello.s
python -m pytest sw/tests
```

Planned additions:

- `host/` — program loader for the RP2350 demo board
- `lib/` — reusable assembly macros (UART, SPI, I2C, ...)

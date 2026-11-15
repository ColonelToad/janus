# JANUS testbench

This directory contains the cocotb smoke test and the Tiny Tapeout test harness.

## Layout

- `test.py` — cocotb test that drives the DUT
- `tb.v` — testbench wrapper, instantiates `tt_um_coloneltoad_janus`
- `Makefile` — cocotb + simulator configuration
- `requirements.txt` — Python dependencies

## How to run

RTL simulation with Icarus Verilog:

```sh
make -B
```

RTL simulation with Verilator:

```sh
make -B SIM=verilator
```

Gate-level simulation (after hardening):

1. Copy the final gate-level netlist to `gate_level_netlist.v`.
2. Set `PDK_ROOT` to the IHP Open PDK checkout.
3. Run:

```sh
make -B GATES=yes
```

If you want a VCD waveform instead of FST:

```sh
make -B FST=
```

## Viewing waveforms

Using GTKWave:

```sh
gtkwave tb.fst tb.gtkw
```

Using Surfer:

```sh
surfer tb.fst
```

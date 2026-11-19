# SPDX-FileCopyrightText: © 2026 Christopher Onyiuke
# SPDX-License-Identifier: Apache-2.0

"""Gate-level smoke test.

The post-layout netlist has no simulation-only debug port, so this checks the
pins instead: a short program drives both output ports and halts, which proves
the core fetched, decoded, stored to the I/O block and reached HALT.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ClockCycles

sys.path.insert(0, str(Path(__file__).resolve().parent))

import janus_harness as H  # noqa: E402

SMOKE_SRC = """
        LI32 r1, 0x8000
        LI32 r2, 0x00FF0000
        SW   r2, 0x0C(r1)
        LI32 r2, 0x005AA500
        SW   r2, 0x08(r1)
        HALT
"""


@cocotb.test()
async def test_gate_level_pins(dut):
    program = H.assemble(SMOKE_SRC, H.ISA)
    H.start_clock(dut)
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 4)
    H.load_image(dut, program)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 40)

    assert int(dut.uo_out.value) == 0xA5
    assert int(dut.uio_out.value) == 0x5A
    assert int(dut.uio_oe.value) == 0xFF

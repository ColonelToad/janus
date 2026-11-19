# SPDX-FileCopyrightText: © 2026 Christopher Onyiuke
# SPDX-License-Identifier: Apache-2.0

"""Cocotb tests for the JANUS core, memories and pin block."""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ClockCycles, RisingEdge

sys.path.insert(0, str(Path(__file__).resolve().parent))

import janus_harness as H  # noqa: E402

# ---------------------------------------------------------------------------
# Lockstep programs
# ---------------------------------------------------------------------------

ALU_MEM_SRC = """
        .org 0
        LI    r1, 10
        LI    r2, 3
        ADD   r3, r1, r2
        SUB   r4, r2, r1
        AND   r5, r1, r2
        OR    r6, r1, r2
        XOR   r7, r1, r2
        SLL   r8, r1, r2
        SRL   r9, r8, r2
        SRA   r10, r4, r2
        SLT   r11, r4, r2
        SLTU  r12, r2, r1
        NOT   r13, r2
        ADDI  r14, r13, 1
        LI    r1, 0x100
        SW    r3, 0(r1)
        SW    r4, 4(r1)
        SB    r7, 8(r1)
        SH    r5, 10(r1)
        LB    r5, 4(r1)
        LBU   r6, 4(r1)
        LH    r7, 10(r1)
        LHU   r8, 10(r1)
        BNE   r1, r2, skip
        LI    r9, 0xBAD
skip:   CALL  sub
        HALT
sub:    ADDI  r9, r9, 1
        JR    r15
"""

WAIT_SRC = """
        .org 0
        LI    r1, 0
        LI    r2, 3
loop0:  ADDI  r1, r1, 1
        WAITREL r2
        JMP   loop0
ctx1:   LI    r3, 0
        LI    r4, 5
loop1:  ADDI  r3, r3, 1
        WAITREL r4
        JMP   loop1
"""

ABS_WAIT_SRC = """
        .org 0
        LI     r1, 20
        WAITABS r1
        LI     r2, 7
        HALT
"""

LOOP_SRC = """
        .org 0
        HALT
ctx1:   LI    r1, 0
loop:   ADDI  r1, r1, 1
        JMP   loop
"""


@cocotb.test()
async def test_alu_memory_and_control(dut):
    """ALU, loads/stores of all widths, branches and a subroutine call."""
    machine = await H.run_lockstep(dut, ALU_MEM_SRC, cycles=120)
    assert machine.all_halted()
    regs = machine.contexts[0].regs
    assert regs[3] == 13
    assert regs[4] == 0xFFFFFFF9
    assert regs[9] == 11
    assert regs[10] == 0xFFFFFFFF
    assert regs[11] == 1
    assert regs[12] == 1
    assert regs[14] == 0xFFFFFFFD
    assert regs[5] == 0xFFFFFFF9
    assert regs[6] == 0xF9


@cocotb.test()
async def test_relative_waits_two_contexts(dut):
    """Two contexts keep independent REL waits and interleave deterministically."""
    source = WAIT_SRC
    program = H.assemble(source, H.ISA)
    machine = await H.run_lockstep(
        dut,
        source,
        cycles=220,
        entry1=program.symbols["ctx1"],
    )
    assert machine.contexts[0].regs[1] > 0
    assert machine.contexts[1].regs[3] > 0
    # Context 1 waits longer, so it must have advanced less often.
    assert machine.contexts[0].regs[1] > machine.contexts[1].regs[3]


@cocotb.test()
async def test_absolute_wait(dut):
    """WAITABS compares against the global cycle counter."""
    machine = await H.run_lockstep(dut, ABS_WAIT_SRC, cycles=80)
    assert machine.all_halted()
    event = [e for e in machine.trace if e.mnemonic == "WAITABS"][0]
    assert event.cycle == 4
    assert machine.contexts[0].regs[2] == 7


@cocotb.test()
async def test_halt_stops_the_context(dut):
    """A halted context stops retiring instructions while the other runs."""
    program = H.assemble(LOOP_SRC, H.ISA)
    machine = await H.run_lockstep(
        dut, LOOP_SRC, cycles=100, entry1=program.symbols["ctx1"]
    )
    assert machine.contexts[0].halted is True
    assert machine.contexts[1].halted is False
    assert machine.contexts[1].regs[1] > 20


@cocotb.test()
async def test_pins_and_memory_mapped_io(dut):
    """PIN_DIR/PIN_OUT, SET/CLR/XOR and PIN_IN readback."""
    source = """
        LI32  r1, 0x8000
        LI32  r2, 0x00FF0000
        SW    r2, 0x0C(r1)
        LI32  r2, 0x00A50000
        SW    r2, 0x08(r1)
        LI    r5, 10
        WAITREL r5
        LW    r3, 0x04(r1)
        LI32  r2, 0x00000100
        SW    r2, 0x08(r1)
        SW    r2, 0x10(r1)
        LI32  r4, 0x00000200
        SW    r4, 0x10(r1)
        SW    r4, 0x18(r1)
        SW    r4, 0x14(r1)
        HALT
    """
    program = H.assemble(source, H.ISA)
    H.start_clock(dut)
    dut.ena.value = 1
    dut.ui_in.value = 0x3C
    dut.uio_in.value = 0x0F
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 4)
    H.load_image(dut, program)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 80)

    state = H.rtl_state(dut)
    assert state["halted"][0] == 1
    assert state["regs"][0][3] == 0x000F003C
    assert int(dut.uio_oe.value) == 0xFF
    assert int(dut.uio_out.value) == 0x00
    # Final PIN_OUT: 0x100 then SET 0x100, SET 0x200, XOR 0x200, CLR 0x200.
    assert int(dut.uo_out.value) == 0x01

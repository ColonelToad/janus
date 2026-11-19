"""Reusable cocotb helpers for the JANUS RTL.

The central idea is lockstep: the same assembly source runs on the RTL and on
the Python ISS, and after every clock edge the two architectural states must be
identical. The RTL starts issuing two cycles later than the ISS because the
SRAM read and the instruction register add a pipe stage, so the ISS is started
at cycle 2 and the comparison begins once the RTL has completed cycle 2.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sw"))

from janus.assembler import Program, assemble  # noqa: E402
from janus.isa import default_isa  # noqa: E402
from janus.iss import Machine  # noqa: E402

BOOT_DELAY = 2  # RTL cycles of pipe fill before the first instruction retires

ISA = default_isa()


def load_image(dut, program: Program) -> None:
    """Preload instruction and data memory through the behavioural models."""
    for i in range(1024):
        dut.user_project.u_imem.u_sram.mem[i].value = program.words[i] if i < len(program.words) else 0
    for i in range(512):
        dut.user_project.u_dmem.u_sram.mem[i].value = 0


def set_entry(dut, context: int, pc: int) -> None:
    """Set a context's reset PC while the core is held in reset.

    The bootloader will own this in hardware; until it exists the testbench
    pokes the register directly.
    """
    dut.user_project.u_core.pc[context].value = pc


def start_clock(dut, period_ns: int = 20) -> None:
    cocotb.start_soon(Clock(dut.clk, period_ns, unit="ns").start())


async def reset(dut, *, cycles: int = 4) -> None:
    """Hold reset low long enough for every synchroniser to settle."""
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1


def rtl_state(dut) -> dict:
    """Snapshot the architectural state the debug port exposes."""
    regs = int(dut.user_project.u_core.dbg_regs.value)
    pcs = int(dut.user_project.u_core.dbg_pc.value)
    return {
        "regs": [
            [(regs >> (ctx * 512 + reg * 32)) & 0xFFFFFFFF for reg in range(16)]
            for ctx in range(2)
        ],
        "pc": [(pcs >> (ctx * 32)) & 0xFFFFFFFF for ctx in range(2)],
        "waiting": [int(dut.user_project.u_core.dbg_waiting.value) >> ctx & 1 for ctx in range(2)],
        "halted": [int(dut.user_project.u_core.dbg_halted.value) >> ctx & 1 for ctx in range(2)],
    }


def iss_state(machine: Machine) -> dict:
    return {
        "regs": [list(ctx.regs) for ctx in machine.contexts],
        "pc": [ctx.pc for ctx in machine.contexts],
        "waiting": [int(ctx.waiting) for ctx in machine.contexts],
        "halted": [int(ctx.halted) for ctx in machine.contexts],
    }


def compare(dut, machine: Machine, cycle: int) -> None:
    rtl = rtl_state(dut)
    ref = iss_state(machine)
    for ctx in range(2):
        assert rtl["pc"][ctx] == ref["pc"][ctx], (
            f"cycle {cycle} ctx {ctx}: pc {rtl['pc'][ctx]:#x} != {ref['pc'][ctx]:#x}"
        )
        for reg in range(16):
            assert rtl["regs"][ctx][reg] == ref["regs"][ctx][reg], (
                f"cycle {cycle} ctx {ctx} r{reg}: "
                f"{rtl['regs'][ctx][reg]:#x} != {ref['regs'][ctx][reg]:#x}"
            )
        assert rtl["waiting"][ctx] == ref["waiting"][ctx], (
            f"cycle {cycle} ctx {ctx}: waiting {rtl['waiting'][ctx]} != {ref['waiting'][ctx]}"
        )
        assert rtl["halted"][ctx] == ref["halted"][ctx], (
            f"cycle {cycle} ctx {ctx}: halted {rtl['halted'][ctx]} != {ref['halted'][ctx]}"
        )


def compare_memory(dut, machine: Machine) -> None:
    for i in range(512):
        word = int(dut.user_project.u_dmem.u_sram.mem[i].value)
        ref = int.from_bytes(machine.data[i * 4 : i * 4 + 4], "little")
        assert word == ref, f"dmem word {i:#x}: {word:#x} != {ref:#x}"


async def run_lockstep(
    dut,
    source: str,
    *,
    cycles: int = 200,
    entry1: int | None = 0,
    entry0: int = 0,
) -> Machine:
    """Run `source` on RTL and ISS and assert the states stay identical."""
    program = assemble(source, ISA)
    machine = Machine(
        ISA, program, entry0=entry0, entry1=entry1, start_cycle=BOOT_DELAY
    )

    start_clock(dut)
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 4)

    # Load while the core is held in reset, then release it.
    load_image(dut, program)
    if entry1 is not None:
        set_entry(dut, 1, entry1)
    if entry0 != 0:
        set_entry(dut, 0, entry0)
    dut.rst_n.value = 1

    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(dut.user_project.cycle.value) == 1, "cycle counter did not start at zero"

    completed = 0
    while completed < cycles:
        if completed >= BOOT_DELAY:
            assert machine.cycle == completed, (
                f"model at cycle {machine.cycle}, RTL at {completed}"
            )
            machine.tick()
            compare(dut, machine, completed)
        await RisingEdge(dut.clk)
        await ReadOnly()
        completed += 1

    compare_memory(dut, machine)
    return machine

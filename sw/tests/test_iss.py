from pathlib import Path

import pytest

from janus.assembler import assemble, assemble_file
from janus.isa import default_isa
from janus.iss import IssError, Machine

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def isa():
    return default_isa()


def test_hello_writes_memory(isa):
    program = assemble_file(REPO / "programs" / "hello.s", isa)
    machine = Machine(isa, program)
    machine.run()
    assert machine.all_halted()
    for i in range(10):
        word = int.from_bytes(machine.data[0x100 + 4 * i : 0x104 + 4 * i], "little")
        assert word == i


def test_single_context_issues_on_even_cycles(isa):
    machine = Machine.from_source("LI r1, 1\nADDI r1, r1, 1\nHALT\n", isa)
    machine.run()
    assert machine.all_halted()
    assert [event.cycle for event in machine.trace] == [0, 2, 4]
    assert all(event.context == 0 for event in machine.trace)
    assert machine.contexts[0].regs[1] == 2


def test_two_contexts_interleave(isa):
    program = assemble_file(REPO / "programs" / "two_contexts.s", isa)
    machine = Machine(
        isa,
        program,
        entry0=program.symbols["ctx0"],
        entry1=program.symbols["ctx1"],
    )
    machine.run(200)
    assert not machine.all_halted()
    # Every event happens in its context's slot.
    assert all(event.cycle % 2 == event.context for event in machine.trace)
    # Each context keeps its own registers.
    assert machine.contexts[0].regs[3] == 16
    assert machine.contexts[1].regs[3] == 26
    # The two loops run at their programmed periods.
    ctx0_stores = [e.cycle for e in machine.trace if e.context == 0 and e.mnemonic == "SW"]
    ctx1_stores = [e.cycle for e in machine.trace if e.context == 1 and e.mnemonic == "SW"]
    assert ctx0_stores[1] - ctx0_stores[0] == 20
    assert ctx1_stores[1] - ctx1_stores[0] == 30


def test_waitrel_stalls_only_the_waiting_context(isa):
    # Context 0 waits; context 1 spins on a normal loop.
    program = assemble(
        """
        .org 0x40
        LI r1, 100
        WAITREL r1
        LI r2, 1
        HALT
        .org 0x80
    spin: JMP spin
        """,
        isa,
    )
    machine = Machine(isa, program, entry0=0x40, entry1=0x80)
    machine.run(120)
    ctx0 = [e.cycle for e in machine.trace if e.context == 0]
    ctx1 = [e.cycle for e in machine.trace if e.context == 1]
    # Context 0 is stalled after the WAITREL, so it issues far fewer instructions.
    assert len(ctx1) > len(ctx0)
    # Context 1 keeps issuing every odd cycle.
    assert ctx1[:6] == [1, 3, 5, 7, 9, 11]


def test_waitpin_wakes_on_edge(isa):
    machine = Machine.from_source(
        """
        LI32 r1, 0x8000
        LI r2, 1
        LI r3, 0
        WAITPIN r2, r3
        HALT
        """,
        isa,
    )
    machine.run(20)
    assert not machine.all_halted()
    machine.set_pin_in(0x0001)
    machine.run(20)
    assert machine.all_halted()


def test_waitpin_timeout(isa):
    machine = Machine.from_source(
        """
        LI32 r1, 0x8000
        LI r2, 1
        LI r4, 0x10
        WAITPIN r2, r4
        HALT
        """,
        isa,
    )
    machine.run(30)
    assert machine.all_halted()


def test_pin_set_clear_xor(isa):
    machine = Machine.from_source(
        """
        LI32 r1, 0x8000
        LI32 r2, 0x0100
        SW r2, 0x10(r1)
        SW r2, 0x14(r1)
        SW r2, 0x18(r1)
        HALT
        """,
        isa,
    )
    machine.run()
    assert machine.pin_out & 0x0100
    assert machine.pin_level(8) == 1


def test_cycle_register(isa):
    machine = Machine.from_source(
        """
        LI32 r1, 0x8000
        LW r2, 0(r1)
        HALT
        """,
        isa,
    )
    machine.run()
    # LI32 is two instructions, so the load issues at cycle 4.
    assert machine.contexts[0].regs[2] == 4


def test_ctx_id(isa):
    machine = Machine.from_source(
        """
        LI32 r1, 0x8000
        LW r2, 0x20(r1)
        HALT
        """,
        isa,
    )
    machine.run()
    assert machine.contexts[0].regs[2] == 0


def test_boot_request_stops_the_machine(isa):
    machine = Machine.from_source(
        """
        LI32 r1, 0x8000
        LI32 r2, 0x4A4E5553
        SW r2, 0x24(r1)
        HALT
        """,
        isa,
    )
    machine.run()
    assert machine.boot_requested
    assert machine.stopped


def test_data_memory_bounds(isa):
    machine = Machine.from_source(
        """
        LI r1, 0x9000
        SW r1, 0(r1)
        """,
        isa,
    )
    with pytest.raises(IssError, match="outside memory"):
        machine.run()


def test_call_and_ret(isa):
    machine = Machine.from_source(
        """
        .org 0
        CALL r15, fn
        HALT
        .org 0x20
    fn: LI r1, 42
        RET
        """,
        isa,
    )
    machine.run()
    assert machine.all_halted()
    assert machine.contexts[0].regs[1] == 42
    assert machine.contexts[0].regs[15] == 1

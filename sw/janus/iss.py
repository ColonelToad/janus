"""Cycle-accurate instruction-set simulator for JANUS.

The ISS mirrors the RTL timing model: with two contexts, context 0 issues on
even cycles and context 1 on odd cycles. A context that is stalled in a wait
keeps its slot idle, so the cycle at which every instruction issues is fully
determined by the program.

The ISS is the reference model for RTL/ISS lockstep tests. It is intentionally
written for clarity rather than raw speed; firmware images are small.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .assembler import Program
from .isa import ISA, sign_extend, to_u32

# Pin masks derived from the 24-pin map in isa.yaml.
INPUT_MASK = 0x00FF00FF   # pins 0..7 (ui_in) and 16..23 (uio)
OUTPUT_MASK = 0x00FFFF00  # pins 8..15 (uo_out) and 16..23 (uio)
BIDIR_MASK = 0x00FF0000   # pins 16..23 (uio)

BOOT_MAGIC = 0x4A4E5553


class IssError(Exception):
    """Raised when the simulated program does something the RTL forbids."""


@dataclass
class Context:
    index: int
    regs: list[int] = field(default_factory=lambda: [0] * 16)
    pc: int = 0
    waiting: bool = False
    halted: bool = False
    deadline: int = 0
    wait_has_deadline: bool = False
    wait_pin_mask: int = 0
    cycles_issued: int = 0
    # The data SRAM returns one cycle after the address, so a load reaches the
    # register file at the start of the load cycle + 2. Architectural results
    # are unchanged, but cycle-by-cycle lockstep with the RTL needs the delay.
    pending_rd: int | None = None
    pending_val: int = 0
    pending_commit: int = 0

    def read(self, index: int) -> int:
        return 0 if index == 0 else self.regs[index]

    def write(self, index: int, value: int) -> None:
        if index != 0:
            self.regs[index] = value & 0xFFFFFFFF


@dataclass
class TraceEvent:
    cycle: int
    context: int
    pc: int
    word: int
    mnemonic: str
    writes: dict[int, int] = field(default_factory=dict)
    mem_writes: list[tuple[int, int]] = field(default_factory=list)
    note: str = ""


class Machine:
    """A two-context JANUS machine."""

    def __init__(self, isa: ISA, program: Program | None = None, *, entry0: int = 0, entry1: int | None = None, start_cycle: int = 0):
        self.isa = isa
        self.data_size = int(isa.memory.get("data", {}).get("size_bytes", 2048))
        self.imem_size = int(isa.memory.get("instruction", {}).get("size_words", 512))
        self.data = bytearray(self.data_size)
        self.imem = [0] * self.imem_size
        self.contexts = [Context(0), Context(1)][: isa.context_count]

        self.cycle = 0
        self.pin_in = 0
        self.pin_out = 0
        self.pin_dir = 0
        self.pin_edge = 0
        self.boot_requested = False
        self.stopped = False
        self.trace: list[TraceEvent] = []
        self.max_cycles = 0
        self._current_writes: dict[int, int] = {}
        self._current_mem_writes: list[tuple[int, int]] = []

        if program is not None:
            self.load_program(program, entry0=entry0, entry1=entry1, start_cycle=start_cycle)

    # -- construction / loading -----------------------------------------
    @classmethod
    def from_source(cls, source: str, isa: ISA, **kwargs) -> "Machine":
        from .assembler import assemble

        program = assemble(source, isa)
        return cls(isa, program, **kwargs)

    def load_program(self, program: Program, *, entry0: int = 0, entry1: int | None = None, start_cycle: int = 0) -> None:
        if len(program.words) > self.imem_size:
            raise IssError(f"program is {len(program.words)} words, memory holds {self.imem_size}")
        self.imem = list(program.words) + [0] * (self.imem_size - len(program.words))
        for context in self.contexts:
            context.regs = [0] * 16
            context.waiting = False
            context.halted = False
            context.deadline = 0
            context.wait_has_deadline = False
            context.wait_pin_mask = 0
            context.cycles_issued = 0
            context.pending_rd = None
            context.pending_val = 0
            context.pending_commit = 0
        self.contexts[0].pc = entry0
        if entry1 is None:
            if len(self.contexts) > 1:
                self.contexts[1].halted = True
        else:
            self.contexts[1].pc = entry1
        self.cycle = start_cycle
        self.trace.clear()
        self.stopped = False
        self.boot_requested = False

    # -- external pin interface -----------------------------------------
    def set_pin_in(self, value: int) -> None:
        """Drive the input-capable pins and update the sticky edge flags."""
        value &= INPUT_MASK
        changed = value ^ self.pin_in
        self.pin_in = value
        self.pin_edge |= changed

    def pin_level(self, index: int) -> int:
        mask = 1 << index
        if 8 <= index <= 15:
            return 1 if self.pin_out & mask else 0
        if index >= 16 and (self.pin_dir & mask):
            return 1 if self.pin_out & mask else 0
        return 1 if self.pin_in & mask else 0

    # -- execution -------------------------------------------------------
    def all_halted(self) -> bool:
        return all(context.halted for context in self.contexts)

    def run(self, max_cycles: int | None = None, *, stop_when: Callable[["Machine"], bool] | None = None) -> "Machine":
        """Run for at most ``max_cycles`` additional cycles.

        Stops early when every context has halted, when the bootloader is
        requested, or when ``stop_when`` returns true.
        """
        limit = max_cycles if max_cycles is not None else 10_000_000
        start = self.cycle
        self.max_cycles = limit
        while self.cycle - start < limit:
            if self.all_halted() or self.stopped:
                break
            if stop_when is not None and stop_when(self):
                break
            self.tick()
        return self

    def tick(self) -> None:
        """Advance exactly one global cycle."""
        if self.stopped:
            return
        for context in self.contexts:
            if context.pending_rd is not None and self.cycle >= context.pending_commit:
                context.write(context.pending_rd, context.pending_val)
                context.pending_rd = None
        index = self.cycle % len(self.contexts)
        context = self.contexts[index]
        issued = False
        if not context.halted:
            if context.waiting:
                if self._wake(context):
                    context.waiting = False
                    self._execute(context)
                    issued = True
            else:
                self._execute(context)
                issued = True
        if issued:
            context.cycles_issued += 1
        self.cycle += 1

    def _wake(self, context: Context) -> bool:
        if context.wait_pin_mask and (self.pin_edge & context.wait_pin_mask):
            return True
        if context.wait_has_deadline and self.cycle >= context.deadline:
            return True
        return False

    def _execute(self, context: Context) -> None:
        pc = context.pc
        if not 0 <= pc < self.imem_size:
            raise IssError(f"context {context.index}: pc {pc} out of range")
        word = self.imem[pc]
        try:
            insn, fields = self.isa.decode_word(word)
        except ValueError as exc:
            raise IssError(f"context {context.index} pc {pc}: {exc}") from exc

        self._current_writes = {}
        self._current_mem_writes = []
        next_pc = pc + 1
        name = insn.name
        read = context.read
        write = context.write

        if name == "ADD":
            write(fields["rd"], read(fields["rs1"]) + read(fields["rs2"]))
        elif name == "SUB":
            write(fields["rd"], read(fields["rs1"]) - read(fields["rs2"]))
        elif name == "AND":
            write(fields["rd"], read(fields["rs1"]) & read(fields["rs2"]))
        elif name == "OR":
            write(fields["rd"], read(fields["rs1"]) | read(fields["rs2"]))
        elif name == "XOR":
            write(fields["rd"], read(fields["rs1"]) ^ read(fields["rs2"]))
        elif name == "SLL":
            write(fields["rd"], read(fields["rs1"]) << (read(fields["rs2"]) & 31))
        elif name == "SRL":
            write(fields["rd"], (read(fields["rs1"]) & 0xFFFFFFFF) >> (read(fields["rs2"]) & 31))
        elif name == "SRA":
            write(fields["rd"], to_signed(read(fields["rs1"])) >> (read(fields["rs2"]) & 31))
        elif name == "SLT":
            write(fields["rd"], int(to_signed(read(fields["rs1"])) < to_signed(read(fields["rs2"]))))
        elif name == "SLTU":
            write(fields["rd"], int(read(fields["rs1"]) < read(fields["rs2"])))
        elif name == "NOT":
            write(fields["rd"], ~read(fields["rs1"]))
        elif name == "ADDI":
            write(fields["rd"], read(fields["rs1"]) + sign_extend(fields["imm16"], 16))
        elif name == "ANDI":
            write(fields["rd"], read(fields["rs1"]) & fields["imm16"])
        elif name == "ORI":
            write(fields["rd"], read(fields["rs1"]) | fields["imm16"])
        elif name == "XORI":
            write(fields["rd"], read(fields["rs1"]) ^ fields["imm16"])
        elif name == "SLTI":
            write(fields["rd"], int(to_signed(read(fields["rs1"])) < sign_extend(fields["imm16"], 16)))
        elif name == "SLTIU":
            write(fields["rd"], int(read(fields["rs1"]) < (sign_extend(fields["imm16"], 16) & 0xFFFFFFFF)))
        elif name == "LI":
            write(fields["rd"], fields["imm16"])
        elif name == "LUI":
            write(fields["rd"], fields["imm16"] << 16)
        elif name == "SLLI":
            write(fields["rd"], read(fields["rs1"]) << fields["shamt"])
        elif name == "SRLI":
            write(fields["rd"], (read(fields["rs1"]) & 0xFFFFFFFF) >> fields["shamt"])
        elif name == "SRAI":
            write(fields["rd"], to_signed(read(fields["rs1"])) >> fields["shamt"])
        elif name in ("LB", "LH", "LW", "LBU", "LHU"):
            size = {"LB": 1, "LH": 2, "LW": 4, "LBU": 1, "LHU": 2}[name]
            signed = name in ("LB", "LH", "LW")
            address = (read(fields["rs1"]) + sign_extend(fields["imm16"], 16)) & 0xFFFFFFFF
            value = self._load(address, size, signed, context)
            context.pending_rd = fields["rd"]
            context.pending_val = value
            context.pending_commit = self.cycle + 1
            self._current_writes[fields["rd"]] = value
        elif name in ("SB", "SH", "SW"):
            size = {"SB": 1, "SH": 2, "SW": 4}[name]
            address = (read(fields["rs1"]) + sign_extend(fields["imm16"], 16)) & 0xFFFFFFFF
            self._store(address, size, read(fields["rd"]), context)
        elif name == "BEQ":
            if read(fields["rs1"]) == read(fields["rs2"]):
                next_pc = pc + sign_extend(fields["imm16"], 16)
        elif name == "BNE":
            if read(fields["rs1"]) != read(fields["rs2"]):
                next_pc = pc + sign_extend(fields["imm16"], 16)
        elif name == "BLT":
            if to_signed(read(fields["rs1"])) < to_signed(read(fields["rs2"])):
                next_pc = pc + sign_extend(fields["imm16"], 16)
        elif name == "BGE":
            if to_signed(read(fields["rs1"])) >= to_signed(read(fields["rs2"])):
                next_pc = pc + sign_extend(fields["imm16"], 16)
        elif name == "BLTU":
            if read(fields["rs1"]) < read(fields["rs2"]):
                next_pc = pc + sign_extend(fields["imm16"], 16)
        elif name == "BGEU":
            if read(fields["rs1"]) >= read(fields["rs2"]):
                next_pc = pc + sign_extend(fields["imm16"], 16)
        elif name == "JMP":
            next_pc = pc + sign_extend(fields["imm20"], 20)
        elif name == "CALL":
            write(fields["rd"], pc + 1)
            next_pc = pc + sign_extend(fields["imm20"], 20)
        elif name == "JR":
            next_pc = read(fields["rs1"])
        elif name == "WAITABS":
            context.waiting = True
            context.deadline = read(fields["rs1"])
            context.wait_has_deadline = True
            context.wait_pin_mask = 0
        elif name == "WAITREL":
            context.waiting = True
            context.deadline = self.cycle + read(fields["rs1"])
            context.wait_has_deadline = True
            context.wait_pin_mask = 0
        elif name == "WAITPIN":
            mask = read(fields["rs1"]) & INPUT_MASK
            timeout = read(fields["rs2"])
            context.waiting = True
            context.wait_pin_mask = mask
            context.wait_has_deadline = timeout != 0
            context.deadline = self.cycle + timeout
        elif name == "NOP":
            pass
        elif name == "HALT":
            context.halted = True
        else:
            raise IssError(f"unimplemented instruction {name}")

        context.pc = next_pc
        self.trace.append(
            TraceEvent(
                cycle=self.cycle,
                context=context.index,
                pc=pc,
                word=word,
                mnemonic=name,
                writes=dict(self._current_writes),
                mem_writes=list(self._current_mem_writes),
            )
        )

    # -- memory and I/O --------------------------------------------------
    def _load(self, address: int, size: int, signed: bool, context: Context) -> int:
        io = self.isa.memory["io"]
        io_base = int(io["base"])
        io_end = io_base + int(io.get("size_bytes", 256))
        if io_base <= address < io_end:
            if size != 4:
                raise IssError(f"context {context.index}: I/O reads must be word sized")
            return self._io_read(address, context)
        if address + size <= self.data_size:
            value = int.from_bytes(self.data[address : address + size], "little")
            return sign_extend(value, size * 8) if signed else value
        raise IssError(f"context {context.index}: load at {address:#x} outside memory")

    def _store(self, address: int, size: int, value: int, context: Context) -> None:
        io = self.isa.memory["io"]
        io_base = int(io["base"])
        io_end = io_base + int(io.get("size_bytes", 256))
        if io_base <= address < io_end:
            if size != 4:
                raise IssError(f"context {context.index}: I/O writes must be word sized")
            self._io_write(address, value, context)
            return
        if address + size <= self.data_size:
            self.data[address : address + size] = (value & ((1 << (size * 8)) - 1)).to_bytes(size, "little")
            self._current_mem_writes.append((address, size))
            return
        raise IssError(f"context {context.index}: store at {address:#x} outside memory")

    def _io_read(self, address: int, context: Context) -> int:
        if address == self.isa.io_address("CYCLE"):
            return self.cycle & 0xFFFFFFFF
        if address == self.isa.io_address("PIN_IN"):
            return self.pin_in
        if address == self.isa.io_address("PIN_OUT"):
            return self.pin_out
        if address == self.isa.io_address("PIN_DIR"):
            return self.pin_dir
        if address == self.isa.io_address("PIN_EDGE"):
            return self.pin_edge
        if address == self.isa.io_address("CTX_ID"):
            return context.index
        return 0

    def _io_write(self, address: int, value: int, context: Context) -> None:
        value &= 0xFFFFFFFF
        if address == self.isa.io_address("PIN_OUT"):
            self.pin_out = value & OUTPUT_MASK
        elif address == self.isa.io_address("PIN_DIR"):
            self.pin_dir = value & BIDIR_MASK
        elif address == self.isa.io_address("PIN_SET"):
            self.pin_out |= value & OUTPUT_MASK
        elif address == self.isa.io_address("PIN_CLR"):
            self.pin_out &= ~(value & OUTPUT_MASK)
        elif address == self.isa.io_address("PIN_XOR"):
            self.pin_out ^= value & OUTPUT_MASK
        elif address == self.isa.io_address("PIN_EDGE"):
            self.pin_edge &= ~value
        elif address == self.isa.io_address("BOOT_REQ"):
            if value == BOOT_MAGIC:
                self.boot_requested = True
                self.stopped = True
        self._current_mem_writes.append((address, 4))


def to_signed(value: int) -> int:
    return sign_extend(value & 0xFFFFFFFF, 32)

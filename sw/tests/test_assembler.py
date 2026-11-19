from pathlib import Path

import pytest

from janus.assembler import AsmError, assemble, assemble_file
from janus.isa import default_isa

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def isa():
    return default_isa()


def test_li_encoding(isa):
    program = assemble("LI r1, 0x100\nHALT\n", isa)
    assert program.words == [0x19100100, 0x51000000]


def test_alu_encoding(isa):
    program = assemble("ADD r1, r2, r3\n", isa)
    assert program.words == [0x00123000]


def test_load_store_encoding(isa):
    program = assemble("SW r1, 0(r3)\nLW r4, 8(r5)\n", isa)
    assert program.words[0] == 0x2A130000
    insn, fields = isa.decode_word(program.words[1])
    assert insn.name == "LW"
    assert fields["rd"] == 4
    assert fields["rs1"] == 5
    assert fields["imm16"] == 8


def test_branch_offset_is_words(isa):
    program = assemble(
        """
        .org 0
    start: NOP
           BNE r1, r2, start
        """,
        isa,
    )
    insn, fields = isa.decode_word(program.words[1])
    assert insn.name == "BNE"
    assert fields["imm16"] == 0xFFFF  # -1: back to the NOP


def test_labels_and_aliases(isa):
    program = assemble(
        """
        .org 0
    loop:  MOV r1, r2
           RET
        """,
        isa,
    )
    assert program.symbols["loop"] == 0
    insn, fields = isa.decode_word(program.words[0])
    assert insn.name == "ADD"
    assert fields["rd"] == 1 and fields["rs1"] == 2 and fields["rs2"] == 0
    insn, fields = isa.decode_word(program.words[1])
    assert insn.name == "JR"
    assert fields["rs1"] == 15


def test_li32_alias(isa):
    program = assemble("LI32 r1, 0xDEADBEEF\n", isa)
    assert len(program.words) == 2
    first, f1 = isa.decode_word(program.words[0])
    second, f2 = isa.decode_word(program.words[1])
    assert first.name == "LUI" and f1["rd"] == 1 and f1["imm16"] == 0xDEAD
    assert second.name == "ORI" and f2["rd"] == 1 and f2["imm16"] == 0xBEEF


def test_directives(isa):
    program = assemble(
        """
        .equ BASE, 0x100
        .org 4
        .word BASE, BASE + 4
        .string "AB"
        """,
        isa,
    )
    assert program.words[0] == 0
    assert program.words[4] == 0x100
    assert program.words[5] == 0x104
    assert program.words[6] == int.from_bytes(b"AB\x00\x00", "little")


def test_hello_program(isa):
    program = assemble_file(REPO / "programs" / "hello.s", isa)
    assert program.words[0] != 0
    assert len(program.words) == 8
    assert "loop" in program.symbols
    assert program.symbols["loop"] == 3


def test_disassembly(isa):
    program = assemble("LI r1, 5\nHALT\n", isa)
    text = "\n".join(program.disassemble(isa))
    assert "LI" in text
    assert "HALT" in text


def test_duplicate_label_rejected(isa):
    with pytest.raises(AsmError, match="duplicate label"):
        assemble("x: NOP\nx: NOP\n", isa)


def test_undefined_symbol_rejected(isa):
    with pytest.raises(AsmError, match="undefined symbol"):
        assemble("JMP nowhere\n", isa)


def test_register_range_rejected(isa):
    with pytest.raises(AsmError, match="out of range"):
        assemble("ADD r16, r1, r2\n", isa)


def test_immediate_range_rejected(isa):
    with pytest.raises(AsmError, match="does not fit"):
        assemble("LI r1, 0x1FFFF\n", isa)


def test_branch_range_rejected(isa):
    with pytest.raises(AsmError, match="does not fit"):
        assemble(".org 0\nNOP\nBNE r1, r2, 0x20000\n", isa)


def test_program_too_large_rejected(isa):
    with pytest.raises(AsmError, match="instruction memory"):
        assemble(".org 512\nNOP\n", isa)

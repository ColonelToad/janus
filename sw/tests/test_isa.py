from janus.isa import default_isa, sign_extend, to_s32, to_u32


def test_isa_loads():
    isa = default_isa()
    assert isa.name == "JANUS"
    assert isa.word_bits == 32
    assert isa.reg_count == 16
    assert isa.context_count == 2
    assert isa.reg_zero == 0
    assert isa.reg_link == 15


def test_opcodes_are_unique_and_known():
    isa = default_isa()
    assert len(isa.by_opcode) == len(isa.instructions)
    for insn in isa.instructions.values():
        assert insn.opcode in isa.by_opcode
        assert insn.format in isa.formats


def test_format_widths():
    isa = default_isa()
    r = isa.formats["R"]
    assert r.width("opcode") == 8
    assert r.width("rd") == 4
    assert r.width("rs1") == 4
    assert r.width("rs2") == 4
    assert isa.formats["J"].width("imm20") == 20
    assert isa.formats["IS"].width("shamt") == 5


def test_encode_decode_roundtrip():
    isa = default_isa()
    word = isa.encode_word("ADD", {"rd": 1, "rs1": 2, "rs2": 3})
    assert word == 0x00123000
    insn, fields = isa.decode_word(word)
    assert insn.name == "ADD"
    assert fields["rd"] == 1
    assert fields["rs1"] == 2
    assert fields["rs2"] == 3


def test_unknown_opcode_rejected():
    isa = default_isa()
    try:
        isa.decode_word(0xFF000000)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_sign_helpers():
    assert sign_extend(0xFFFF, 16) == -1
    assert sign_extend(0x8000, 16) == -32768
    assert sign_extend(0x7FFF, 16) == 32767
    assert to_s32(0xFFFFFFFF) == -1
    assert to_u32(-1) == 0xFFFFFFFF


def test_io_map_addresses():
    isa = default_isa()
    assert isa.io_address("CYCLE") == 0x8000
    assert isa.io_address("PIN_IN") == 0x8004
    assert isa.io_address("PIN_XOR") == 0x8018
    assert isa.io_address("BOOT_REQ") == 0x8024

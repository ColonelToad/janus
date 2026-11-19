"""JANUS ISA definition loader.

The ISA lives in ``isa/isa.yaml`` at the repository root. This module parses it
once and exposes instruction and format tables that the assembler, the ISS and
the SystemVerilog generator all share.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ISA_PATH = REPO_ROOT / "isa" / "isa.yaml"


@dataclass(frozen=True)
class Operand:
    field: str
    kind: str
    write: bool = False
    ext: str | None = None
    bits: int | None = None
    default: int | None = None


@dataclass(frozen=True)
class Instruction:
    name: str
    opcode: int
    format: str
    operands: tuple[Operand, ...]
    semantics: str = ""

    def operand(self, field_name: str) -> Operand | None:
        for op in self.operands:
            if op.field == field_name:
                return op
        return None


@dataclass(frozen=True)
class Alias:
    name: str
    operands: int
    expands: tuple[str, ...]


@dataclass(frozen=True)
class Format:
    name: str
    fields: dict[str, tuple[int, int]]

    def width(self, field_name: str) -> int:
        msb, lsb = self.fields[field_name]
        return msb - lsb + 1

    def extract(self, word: int, field_name: str) -> int:
        msb, lsb = self.fields[field_name]
        return (word >> lsb) & ((1 << (msb - lsb + 1)) - 1)

    def insert(self, word: int, field_name: str, value: int) -> int:
        msb, lsb = self.fields[field_name]
        width = msb - lsb + 1
        mask = (1 << width) - 1
        return (word & ~(mask << lsb)) | ((value & mask) << lsb)


class ISA:
    """Parsed view of ``isa.yaml``."""

    def __init__(self, data: dict[str, Any], source: Path | None = None):
        self.raw = data
        self.source = source
        self.name: str = data["name"]
        self.version: str = str(data["version"])
        self.word_bits: int = int(data["word_bits"])
        self.address_bits: int = int(data["address_bits"])
        self.instruction_bytes: int = int(data["instruction_bytes"])

        regs = data["registers"]
        self.reg_count: int = int(regs["count"])
        self.reg_width: int = int(regs["width"])
        self.reg_zero: int = int(regs["zero"])
        self.reg_link: int = int(regs["link"])
        self.reg_names: tuple[str, ...] = tuple(regs["names"])

        self.context_count: int = int(data["contexts"]["count"])

        self.formats: dict[str, Format] = {
            name: Format(name=name, fields={f: tuple(v) for f, v in spec["fields"].items()})
            for name, spec in data["formats"].items()
        }

        self.instructions: dict[str, Instruction] = {}
        self.by_opcode: dict[int, Instruction] = {}
        for spec in data["instructions"]:
            insn = Instruction(
                name=spec["name"],
                opcode=int(spec["opcode"]),
                format=spec["format"],
                operands=tuple(
                    Operand(
                        field=op["field"],
                        kind=op["kind"],
                        write=bool(op.get("write", False)),
                        ext=op.get("ext"),
                        bits=op.get("bits"),
                        default=op.get("default"),
                    )
                    for op in spec.get("operands", [])
                ),
                semantics=spec.get("semantics", ""),
            )
            if insn.name in self.instructions:
                raise ValueError(f"duplicate instruction name {insn.name}")
            if insn.opcode in self.by_opcode:
                raise ValueError(f"duplicate opcode {insn.opcode:#04x}")
            if insn.format not in self.formats:
                raise ValueError(f"{insn.name}: unknown format {insn.format}")
            self.instructions[insn.name] = insn
            self.by_opcode[insn.opcode] = insn

        self.aliases: dict[str, Alias] = {
            spec["name"]: Alias(
                name=spec["name"],
                operands=int(spec["operands"]),
                expands=tuple(
                    spec["expands"] if isinstance(spec["expands"], list) else [spec["expands"]]
                ),
            )
            for spec in data.get("aliases", [])
        }

        self.memory = data.get("memory", {})
        self.io: dict[str, dict[str, Any]] = {}
        io_base = int(self.memory.get("io", {}).get("base", 0))
        for reg in self.memory.get("io", {}).get("registers", []):
            self.io[reg["name"]] = {**reg, "address": io_base + int(reg["offset"])}

    # -- lookups ---------------------------------------------------------
    def instruction(self, name: str) -> Instruction:
        key = name.upper()
        if key not in self.instructions:
            raise KeyError(f"unknown instruction {name!r}")
        return self.instructions[key]

    def is_instruction(self, name: str) -> bool:
        return name.upper() in self.instructions

    def is_alias(self, name: str) -> bool:
        return name.upper() in self.aliases

    def io_address(self, name: str) -> int:
        return int(self.io[name.upper()]["address"])

    # -- encode/decode ---------------------------------------------------
    def encode_word(self, name: str, fields: dict[str, int]) -> int:
        insn = self.instruction(name)
        fmt = self.formats[insn.format]
        word = 0
        word = fmt.insert(word, "opcode", insn.opcode)
        for field_name, value in fields.items():
            if field_name not in fmt.fields:
                raise KeyError(f"{insn.name}: field {field_name} not in format {fmt.name}")
            word = fmt.insert(word, field_name, value)
        return word

    def decode_word(self, word: int) -> tuple[Instruction, dict[str, int]]:
        opcode = (word >> 24) & 0xFF
        if opcode not in self.by_opcode:
            raise ValueError(f"unknown opcode {opcode:#04x} in word {word:#010x}")
        insn = self.by_opcode[opcode]
        fmt = self.formats[insn.format]
        fields = {name: fmt.extract(word, name) for name in fmt.fields if name != "opcode"}
        return insn, fields


@functools.lru_cache(maxsize=1)
def default_isa() -> ISA:
    return load_isa(DEFAULT_ISA_PATH)


def load_isa(path: str | Path = DEFAULT_ISA_PATH) -> ISA:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return ISA(data, source=path)


def sign_extend(value: int, bits: int) -> int:
    """Return the signed interpretation of an unsigned ``bits``-wide value."""
    sign_bit = 1 << (bits - 1)
    value &= (1 << bits) - 1
    return (value ^ sign_bit) - sign_bit


def to_u32(value: int) -> int:
    return value & 0xFFFFFFFF


def to_s32(value: int) -> int:
    return sign_extend(value, 32)

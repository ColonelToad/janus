"""Two-pass assembler for the JANUS ISA.

Usage::

    from janus.isa import default_isa
    from janus.assembler import assemble

    program = assemble(source_text, default_isa())
    program.words          # list of 32-bit words
    program.to_bytes()     # little-endian image

The assembler is deliberately small and dependency-free so that it can run in
CI and inside cocotb tests. It supports labels, ``.org``, ``.equ``, ``.word``,
``.align``, ``.space``, ``.fill`` and ``.string`` directives, plus the aliases
declared in ``isa.yaml``.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .isa import ISA, sign_extend

# ---------------------------------------------------------------------------
# errors and data model
# ---------------------------------------------------------------------------


class AsmError(Exception):
    """Assembly failure with source location context."""

    def __init__(self, message: str, line_no: int | None = None, text: str | None = None):
        self.message = message
        self.line_no = line_no
        self.text = text
        location = f"line {line_no}: " if line_no is not None else ""
        detail = f"\n    {text.strip()}" if text else ""
        super().__init__(f"{location}{message}{detail}")


@dataclass(frozen=True)
class ListingEntry:
    pc: int
    value: int
    line_no: int
    source: str


@dataclass
class Program:
    """An assembled image plus symbols and a listing."""

    words: list[int]
    symbols: dict[str, int]
    listing: list[ListingEntry] = field(default_factory=list)
    source_name: str = "<asm>"

    def to_bytes(self) -> bytes:
        out = bytearray()
        for word in self.words:
            out += int(word & 0xFFFFFFFF).to_bytes(4, "little")
        return bytes(out)

    def to_hex(self) -> str:
        return "\n".join(f"{word:08x}" for word in self.words) + ("\n" if self.words else "")

    def disassemble(self, isa: ISA) -> list[str]:
        from .isa import sign_extend as sx

        lines = []
        for entry in self.listing:
            insn, fields = isa.decode_word(entry.value)
            parts = []
            for op in insn.operands:
                value = fields.get(op.field, 0)
                if op.kind == "reg":
                    parts.append(isa.reg_names[value])
                elif op.kind == "label":
                    offset = sx(value, op.bits or 16)
                    parts.append(f"{entry.pc + offset}")
                elif op.kind == "memoff":
                    base = fields.get("rs1", 0)
                    parts.append(f"{sx(value, 16)}({isa.reg_names[base]})")
                elif op.kind == "membase":
                    continue
                else:
                    parts.append(str(value))
            lines.append(f"{entry.pc:04x}: {entry.value:08x}  {insn.name:<7} {', '.join(parts)}")
        return lines


@dataclass
class _Statement:
    line_no: int
    text: str
    label: str | None
    mnemonic: str | None
    operands: list[str]


# ---------------------------------------------------------------------------
# safe expression evaluation
# ---------------------------------------------------------------------------

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.floordiv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
}

_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Invert: operator.invert,
}


def eval_expression(text: str, resolver) -> int:
    """Evaluate an integer expression using a restricted AST walker."""
    text = text.strip()
    if not text:
        raise AsmError("empty expression")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise AsmError(f"bad expression {text!r}: {exc.msg}") from exc

    def walk(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return int(node.value)
            if isinstance(node.value, int):
                return node.value
            if isinstance(node.value, str) and len(node.value) == 1:
                return ord(node.value)
            raise AsmError(f"unsupported constant {node.value!r}")
        if isinstance(node, ast.Name):
            return resolver(node.id)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](walk(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](walk(node.left), walk(node.right))
        raise AsmError(f"unsupported expression element {type(node).__name__}")

    return int(walk(tree))


# ---------------------------------------------------------------------------
# lexical helpers
# ---------------------------------------------------------------------------

_LABEL_RE = re.compile(r"^\s*([A-Za-z_.$][\w.$]*)\s*:\s*(.*)$")
_MEM_RE = re.compile(r"^\s*(.*?)\s*\(\s*([^()]+?)\s*\)\s*$")
_REG_RE = re.compile(r"^(?:r|x)(\d+)$", re.IGNORECASE)


def _strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and quote:
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            continue
        if ch in (";", "#"):
            return line[:i]
    return line


def split_operands(text: str) -> list[str]:
    """Split a comma-separated operand list, respecting parentheses/quotes."""
    if not text.strip():
        return []
    out: list[str] = []
    depth = 0
    quote: str | None = None
    current: list[str] = []
    for ch in text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    out.append("".join(current).strip())
    return [item for item in out if item != ""]


# ---------------------------------------------------------------------------
# assembler
# ---------------------------------------------------------------------------


class Assembler:
    def __init__(self, isa: ISA, *, source_name: str = "<asm>", check_size: bool = True):
        self.isa = isa
        self.source_name = source_name
        self.check_size = check_size
        self.symbols: dict[str, int] = {}
        self.equates: dict[str, str] = {}
        self._resolving: set[str] = set()
        self._statements: list[_Statement] = []
        self._max_pc = 0

    # -- public ----------------------------------------------------------
    def assemble(self, source: str) -> Program:
        self._parse(source)
        self._pass_one()
        return self._pass_two()

    # -- parsing ---------------------------------------------------------
    def _parse(self, source: str) -> None:
        self._statements = []
        for line_no, raw in enumerate(source.splitlines(), start=1):
            text = _strip_comment(raw).rstrip()
            if not text.strip():
                continue
            label = None
            rest = text
            match = _LABEL_RE.match(rest)
            if match:
                label = match.group(1)
                rest = match.group(2)
            rest = rest.strip()
            mnemonic = None
            operands: list[str] = []
            if rest:
                parts = rest.split(None, 1)
                mnemonic = parts[0]
                if len(parts) > 1:
                    operands = split_operands(parts[1])
            self._statements.append(
                _Statement(line_no=line_no, text=text, label=label, mnemonic=mnemonic, operands=operands)
            )

    def _expand_alias(self, mnemonic: str, operands: list[str], depth: int = 0) -> list[tuple[str, list[str]]]:
        if depth > 8:
            raise AsmError(f"alias expansion too deep at {mnemonic}")
        key = mnemonic.upper()
        if key not in self.isa.aliases:
            return [(mnemonic, operands)]
        alias = self.isa.aliases[key]
        if len(operands) != alias.operands:
            raise AsmError(
                f"{alias.name} expects {alias.operands} operands, got {len(operands)}"
            )
        expanded: list[tuple[str, list[str]]] = []
        for line in alias.expands:
            line = line
            for index, value in reversed(list(enumerate(operands))):
                line = line.replace(f"{{{index}}}", value)
            parts = line.split(None, 1)
            sub_mnemonic = parts[0]
            sub_operands = split_operands(parts[1]) if len(parts) > 1 else []
            expanded.extend(self._expand_alias(sub_mnemonic, sub_operands, depth + 1))
        return expanded

    def _instruction_count(self, statement: _Statement) -> int:
        if not statement.mnemonic or statement.mnemonic.startswith("."):
            return 0
        return len(self._expand_alias(statement.mnemonic, statement.operands))

    # -- pass 1 ----------------------------------------------------------
    def _pass_one(self) -> None:
        pc = 0
        for stmt in self._statements:
            if stmt.label:
                if stmt.label in self.symbols:
                    raise AsmError(f"duplicate label {stmt.label!r}", stmt.line_no, stmt.text)
                self.symbols[stmt.label] = pc
            if not stmt.mnemonic:
                continue
            mnemonic = stmt.mnemonic.lower()
            if mnemonic == ".org":
                pc = self._eval(stmt.operands[0], stmt)
            elif mnemonic == ".equ":
                if len(stmt.operands) != 2:
                    raise AsmError(".equ expects NAME, expression", stmt.line_no, stmt.text)
                name = stmt.operands[0].strip()
                if name in self.symbols or name in self.equates:
                    raise AsmError(f"duplicate symbol {name!r}", stmt.line_no, stmt.text)
                self.equates[name] = stmt.operands[1]
            elif mnemonic == ".align":
                align = self._eval(stmt.operands[0], stmt)
                if align <= 0:
                    raise AsmError(".align expects a positive number", stmt.line_no, stmt.text)
                pc = ((pc + align - 1) // align) * align
            elif mnemonic == ".word":
                pc += len(stmt.operands)
            elif mnemonic in (".space", ".fill"):
                count = self._eval(stmt.operands[0], stmt)
                if count < 0:
                    raise AsmError(f"{mnemonic} count must be non-negative", stmt.line_no, stmt.text)
                pc += count
            elif mnemonic == ".string":
                pc += self._string_word_count(stmt)
            elif mnemonic.startswith("."):
                raise AsmError(f"unknown directive {stmt.mnemonic}", stmt.line_no, stmt.text)
            else:
                pc += self._instruction_count(stmt)
            self._max_pc = max(self._max_pc, pc)
        self._max_pc = max(self._max_pc, pc)

    # -- pass 2 ----------------------------------------------------------
    def _pass_two(self) -> Program:
        pc = 0
        words: dict[int, int] = {}
        listing: list[ListingEntry] = []
        for stmt in self._statements:
            if not stmt.mnemonic:
                continue
            mnemonic = stmt.mnemonic.lower()
            if mnemonic == ".org":
                pc = self._eval(stmt.operands[0], stmt)
                continue
            if mnemonic == ".equ":
                continue
            if mnemonic == ".align":
                align = self._eval(stmt.operands[0], stmt)
                pc = ((pc + align - 1) // align) * align
                continue
            if mnemonic == ".word":
                for operand in stmt.operands:
                    value = self._eval(operand, stmt) & 0xFFFFFFFF
                    self._emit(words, listing, pc, value, stmt)
                    pc += 1
                continue
            if mnemonic in (".space", ".fill"):
                count = self._eval(stmt.operands[0], stmt)
                fill = self._eval(stmt.operands[1], stmt) if len(stmt.operands) > 1 else 0
                for _ in range(count):
                    self._emit(words, listing, pc, fill & 0xFFFFFFFF, stmt)
                    pc += 1
                continue
            if mnemonic == ".string":
                for value in self._string_words(stmt):
                    self._emit(words, listing, pc, value, stmt)
                    pc += 1
                continue
            if mnemonic.startswith("."):
                raise AsmError(f"unknown directive {stmt.mnemonic}", stmt.line_no, stmt.text)

            for sub_mnemonic, sub_operands in self._expand_alias(stmt.mnemonic, stmt.operands):
                if not self.isa.is_instruction(sub_mnemonic):
                    raise AsmError(f"unknown instruction {sub_mnemonic!r}", stmt.line_no, stmt.text)
                insn = self.isa.instruction(sub_mnemonic)
                value = self._encode(insn, sub_operands, pc, stmt)
                self._emit(words, listing, pc, value, stmt)
                pc += 1

        if self.check_size:
            limit = int(self.isa.memory.get("instruction", {}).get("size_words", 0))
            if limit and self._max_pc > limit:
                raise AsmError(
                    f"program needs {self._max_pc} words but instruction memory holds {limit}"
                )
        size = max(words) + 1 if words else 0
        image = [words.get(index, 0) for index in range(size)]
        return Program(
            words=image,
            symbols=dict(self.symbols),
            listing=listing,
            source_name=self.source_name,
        )

    # -- encoding --------------------------------------------------------
    def _encode(self, insn, operands: list[str], pc: int, stmt: _Statement) -> int:
        kinds = list(insn.operands)
        fields: dict[str, int] = {}
        expected = sum(1 for kind in kinds if kind.kind != "membase")

        if len(operands) == expected - 1:
            for index, kind in enumerate(kinds):
                if kind.kind == "reg" and kind.default is not None:
                    fields[kind.field] = int(kind.default)
                    kinds = kinds[:index] + kinds[index + 1 :]
                    expected -= 1
                    break
        if len(operands) != expected:
            raise AsmError(
                f"{insn.name} expects {expected} operands, got {len(operands)}",
                stmt.line_no,
                stmt.text,
            )

        op_index = 0
        kind_index = 0
        while kind_index < len(kinds):
            kind = kinds[kind_index]
            if kind.kind == "memoff":
                base_kind = kinds[kind_index + 1]
                text = operands[op_index]
                op_index += 1
                match = _MEM_RE.match(text)
                if not match:
                    raise AsmError(
                        f"expected 'offset(base)' for {insn.name}, got {text!r}",
                        stmt.line_no,
                        stmt.text,
                    )
                imm_text, base_text = match.group(1), match.group(2)
                fields[kind.field] = self._eval(imm_text or "0", stmt)
                fields[base_kind.field] = self._parse_reg(base_text, stmt)
                kind_index += 2
                continue
            if kind.kind == "membase":
                raise AsmError("internal: membase without memoff", stmt.line_no, stmt.text)

            text = operands[op_index]
            op_index += 1
            if kind.kind == "reg":
                fields[kind.field] = self._parse_reg(text, stmt)
            elif kind.kind == "shamt":
                value = self._eval(text, stmt)
                if not 0 <= value <= 31:
                    raise AsmError(f"shift amount {value} out of range", stmt.line_no, stmt.text)
                fields[kind.field] = value
            elif kind.kind == "imm":
                value = self._eval(text, stmt)
                bits = self.isa.formats[insn.format].width(kind.field)
                if not -(1 << (bits - 1)) <= value <= (1 << bits) - 1:
                    raise AsmError(
                        f"immediate {value} does not fit in {bits} bits",
                        stmt.line_no,
                        stmt.text,
                    )
                fields[kind.field] = value
            elif kind.kind == "label":
                target = self._eval(text, stmt)
                offset = target - pc
                bits = kind.bits or self.isa.formats[insn.format].width(kind.field)
                if not -(1 << (bits - 1)) <= offset <= (1 << (bits - 1)) - 1:
                    raise AsmError(
                        f"branch offset {offset} does not fit in {bits} signed bits",
                        stmt.line_no,
                        stmt.text,
                    )
                fields[kind.field] = offset
            else:
                raise AsmError(f"internal: bad operand kind {kind.kind}", stmt.line_no, stmt.text)
            kind_index += 1

        # Immediate fields that were not supplied default to zero.
        for name in self.isa.formats[insn.format].fields:
            if name not in ("opcode",) and name not in fields:
                fields[name] = 0
        return self.isa.encode_word(insn.name, fields)

    # -- helpers ---------------------------------------------------------
    def _emit(self, words: dict[int, int], listing: list[ListingEntry], pc: int, value: int, stmt: _Statement) -> None:
        if pc in words:
            raise AsmError(f"overlapping output at word {pc}", stmt.line_no, stmt.text)
        words[pc] = value
        listing.append(ListingEntry(pc=pc, value=value, line_no=stmt.line_no, source=stmt.text))

    def _parse_reg(self, text: str, stmt: _Statement) -> int:
        text = text.strip()
        match = _REG_RE.match(text)
        if match:
            value = int(match.group(1))
        elif text in self.isa.reg_names:
            value = self.isa.reg_names.index(text)
        else:
            try:
                value = self._eval(text, stmt)
            except AsmError:
                raise AsmError(f"expected a register, got {text!r}", stmt.line_no, stmt.text) from None
        if not 0 <= value < self.isa.reg_count:
            raise AsmError(f"register {value} out of range", stmt.line_no, stmt.text)
        return value

    def _eval(self, text: str, stmt: _Statement) -> int:
        try:
            return eval_expression(text, self._resolve)
        except AsmError as exc:
            if exc.line_no is None:
                raise AsmError(exc.message, stmt.line_no, stmt.text) from None
            raise

    def _resolve(self, name: str) -> int:
        if name in self.symbols:
            return self.symbols[name]
        if name in self.equates:
            if name in self._resolving:
                raise AsmError(f"circular .equ definition involving {name!r}")
            self._resolving.add(name)
            try:
                value = eval_expression(self.equates[name], self._resolve)
            finally:
                self._resolving.discard(name)
            return value
        raise AsmError(f"undefined symbol {name!r}")

    def _string_bytes(self, stmt: _Statement) -> bytes:
        text = stmt.text.split(".string", 1)[1].strip()
        try:
            literal = ast.literal_eval(text)
        except (SyntaxError, ValueError) as exc:
            raise AsmError(f"bad .string literal: {exc}", stmt.line_no, stmt.text) from exc
        if not isinstance(literal, str):
            raise AsmError(".string expects a quoted string", stmt.line_no, stmt.text)
        return literal.encode("utf-8")

    def _string_word_count(self, stmt: _Statement) -> int:
        return (len(self._string_bytes(stmt)) + 3) // 4

    def _string_words(self, stmt: _Statement) -> list[int]:
        data = self._string_bytes(stmt)
        padded = data + b"\x00" * ((4 - len(data) % 4) % 4)
        return [int.from_bytes(padded[i : i + 4], "little") for i in range(0, len(padded), 4)]


def assemble(source: str, isa: ISA, *, source_name: str = "<asm>", check_size: bool = True) -> Program:
    return Assembler(isa, source_name=source_name, check_size=check_size).assemble(source)


def assemble_file(path: str | Path, isa: ISA, *, check_size: bool = True) -> Program:
    path = Path(path)
    return assemble(
        path.read_text(encoding="utf-8"),
        isa,
        source_name=str(path),
        check_size=check_size,
    )

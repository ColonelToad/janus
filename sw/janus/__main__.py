"""Command-line front end for the JANUS toolchain.

    python -m janus asm programs/hello.s -o hello.bin
    python -m janus run programs/hello.s --trace
    python -m janus disasm hello.bin
    python -m janus isa
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .assembler import AsmError, assemble_file
from .isa import default_isa
from .iss import IssError, Machine


def _load_isa():
    try:
        return default_isa()
    except OSError as exc:
        print(f"error: cannot read isa/isa.yaml: {exc}", file=sys.stderr)
        raise SystemExit(2)


def cmd_asm(args: argparse.Namespace) -> int:
    isa = _load_isa()
    program = assemble_file(args.source, isa, check_size=not args.no_size_check)
    if args.hex:
        text = program.to_hex()
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    else:
        data = program.to_bytes()
        if args.output:
            Path(args.output).write_bytes(data)
        else:
            sys.stdout.buffer.write(data)
    if args.symbols:
        for name, value in sorted(program.symbols.items(), key=lambda item: item[1]):
            print(f"{value:04x} {name}", file=sys.stderr)
    return 0


def cmd_disasm(args: argparse.Namespace) -> int:
    isa = _load_isa()
    path = Path(args.image)
    if path.suffix in (".hex", ".txt"):
        words = [int(line, 16) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        data = path.read_bytes()
        words = [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data) - 3, 4)]
    for pc, word in enumerate(words):
        try:
            insn, fields = isa.decode_word(word)
        except ValueError:
            print(f"{pc:04x}: {word:08x}  .word {word:#010x}")
            continue
        parts = []
        index = 0
        while index < len(insn.operands):
            op = insn.operands[index]
            value = fields.get(op.field, 0)
            if op.kind == "memoff":
                base = fields.get(insn.operands[index + 1].field, 0)
                parts.append(f"{value}({isa.reg_names[base]})")
                index += 2
                continue
            if op.kind == "membase":
                index += 1
                continue
            if op.kind == "reg":
                parts.append(isa.reg_names[value])
            elif op.kind == "label":
                bits = op.bits or 16
                sign = 1 << (bits - 1)
                offset = (value ^ sign) - sign
                parts.append(f"{pc + offset}")
            else:
                parts.append(str(value))
            index += 1
        print(f"{pc:04x}: {word:08x}  {insn.name:<7} {', '.join(parts)}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    isa = _load_isa()
    program = assemble_file(args.source, isa)
    entry0 = program.symbols.get(args.entry0, 0) if args.entry0 else 0
    entry1 = None
    if args.entry1:
        if args.entry1 not in program.symbols:
            print(f"error: no label {args.entry1!r}", file=sys.stderr)
            return 2
        entry1 = program.symbols[args.entry1]
    machine = Machine(isa, program, entry0=entry0, entry1=entry1)
    machine.run(args.cycles)
    for event in machine.trace:
        if args.trace:
            writes = " ".join(f"r{reg}={value:#x}" for reg, value in event.writes.items())
            print(f"{event.cycle:6d} ctx{event.context} {event.pc:04x} {event.mnemonic:<7} {writes}")
    print(f"halted={machine.all_halted()} cycles={machine.cycle}")
    for context in machine.contexts:
        print(
            f"ctx{context.index}: issued={context.cycles_issued} pc={context.pc:04x} "
            f"halted={context.halted} regs="
            + " ".join(f"{value:#x}" for value in context.regs)
        )
    data = machine.data[: args.dump]
    if args.dump:
        print("data:", data.hex())
    return 0


def cmd_isa(args: argparse.Namespace) -> int:
    isa = _load_isa()
    print(f"{isa.name} v{isa.version}: {len(isa.instructions)} instructions, {isa.context_count} contexts")
    for insn in sorted(isa.instructions.values(), key=lambda item: item.opcode):
        print(f"  {insn.opcode:#04x}  {insn.name:<7} {insn.format:<4} {insn.semantics}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="janus", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    asm = sub.add_parser("asm", help="assemble a source file")
    asm.add_argument("source", type=Path)
    asm.add_argument("-o", "--output", type=Path)
    asm.add_argument("--hex", action="store_true", help="write hexadecimal text instead of binary")
    asm.add_argument("--symbols", action="store_true", help="print the symbol table to stderr")
    asm.add_argument("--no-size-check", action="store_true")
    asm.set_defaults(func=cmd_asm)

    disasm = sub.add_parser("disasm", help="disassemble a binary or hex image")
    disasm.add_argument("image", type=Path)
    disasm.set_defaults(func=cmd_disasm)

    run = sub.add_parser("run", help="assemble and run a program on the ISS")
    run.add_argument("source", type=Path)
    run.add_argument("--cycles", type=int, default=None)
    run.add_argument("--trace", action="store_true")
    run.add_argument("--entry0", default=None)
    run.add_argument("--entry1", default=None)
    run.add_argument("--dump", type=int, default=0, help="hex dump this many bytes of data memory")
    run.set_defaults(func=cmd_run)

    isa_cmd = sub.add_parser("isa", help="print the instruction set")
    isa_cmd.set_defaults(func=cmd_isa)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (AsmError, IssError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

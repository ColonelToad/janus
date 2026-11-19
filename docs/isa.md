# JANUS ISA reference (v0.1.0)

> Generated from [`isa/isa.yaml`](../isa/isa.yaml) by `tools/gen_isa.py`. Do not edit by hand.

A small, deterministic 32-bit ISA for software-defined protocol emulation. Two hardware contexts are issued on alternating cycles, so firmware can place pin transitions on exact cycles and run independent protocol engines side by side.

## Registers

16 general-purpose 32-bit registers per context. `r0` always reads as zero; writes to it are discarded. `r15` is the default link register for `CALL`.

| Register | Name | Notes |
| --- | --- | --- |
| `r0` | r0 | hardwired zero |
| `r1` | r1 |  |
| `r2` | r2 |  |
| `r3` | r3 |  |
| `r4` | r4 |  |
| `r5` | r5 |  |
| `r6` | r6 |  |
| `r7` | r7 |  |
| `r8` | r8 |  |
| `r9` | r9 |  |
| `r10` | r10 |  |
| `r11` | r11 |  |
| `r12` | r12 |  |
| `r13` | r13 |  |
| `r14` | r14 |  |
| `r15` | r15 | link register by convention |

## Contexts and timing

Strict barrel interleave. Context 0 may issue on even cycles and context 1 on odd cycles. A stalled context does not give its slot to the other context, so the timing of every issued instruction is predictable.

The global cycle counter is readable at `CYCLE`. `WAITREL rs` stalls the issuing context until the counter reaches the issue cycle plus `rs`; `WAITABS rs` waits for an absolute cycle; `WAITPIN rs1, rs2` waits for an edge on the pins selected by `rs1`, with an optional absolute timeout in `rs2` (zero means no timeout).

## Instruction formats

| Format | Fields (MSB:LSB) |
| --- | --- |
| `R` | `opcode` 31:24, `rd` 23:20, `rs1` 19:16, `rs2` 15:12, `funct` 11:0 |
| `I` | `opcode` 31:24, `rd` 23:20, `rs1` 19:16, `imm16` 15:0 |
| `IS` | `opcode` 31:24, `rd` 23:20, `rs1` 19:16, `shamt` 12:8 |
| `M` | `opcode` 31:24, `rd` 23:20, `rs1` 19:16, `imm16` 15:0 |
| `B` | `opcode` 31:24, `rs1` 23:20, `rs2` 19:16, `imm16` 15:0 |
| `J` | `opcode` 31:24, `rd` 23:20, `imm20` 19:0 |
| `SYS` | `opcode` 31:24 |

## Instructions

| Mnemonic | Opcode | Format | Syntax | Semantics |
| --- | --- | --- | --- | --- |
| `ADD` | `0x00` | `R` | `add rd, rs1, rs2` | rd = rs1 + rs2 |
| `SUB` | `0x01` | `R` | `sub rd, rs1, rs2` | rd = rs1 - rs2 |
| `AND` | `0x02` | `R` | `and rd, rs1, rs2` | rd = rs1 & rs2 |
| `OR` | `0x03` | `R` | `or rd, rs1, rs2` | rd = rs1 \| rs2 |
| `XOR` | `0x04` | `R` | `xor rd, rs1, rs2` | rd = rs1 ^ rs2 |
| `SLL` | `0x05` | `R` | `sll rd, rs1, rs2` | rd = rs1 << (rs2 & 31) |
| `SRL` | `0x06` | `R` | `srl rd, rs1, rs2` | rd = rs1 >> (rs2 & 31), logical |
| `SRA` | `0x07` | `R` | `sra rd, rs1, rs2` | rd = rs1 >> (rs2 & 31), arithmetic |
| `SLT` | `0x08` | `R` | `slt rd, rs1, rs2` | rd = (signed)rs1 < (signed)rs2 ? 1 else 0 |
| `SLTU` | `0x09` | `R` | `sltu rd, rs1, rs2` | rd = rs1 < rs2 ? 1 else 0, unsigned |
| `NOT` | `0x0A` | `R` | `not rd, rs1` | rd = ~rs1 |
| `ADDI` | `0x10` | `I` | `addi rd, rs1, imm16` | rd = rs1 + sign_extend(imm16) |
| `ANDI` | `0x11` | `I` | `andi rd, rs1, imm16` | rd = rs1 & zero_extend(imm16) |
| `ORI` | `0x12` | `I` | `ori rd, rs1, imm16` | rd = rs1 \| zero_extend(imm16) |
| `XORI` | `0x13` | `I` | `xori rd, rs1, imm16` | rd = rs1 ^ zero_extend(imm16) |
| `SLLI` | `0x14` | `IS` | `slli rd, rs1, shamt` | rd = rs1 << shamt |
| `SRLI` | `0x15` | `IS` | `srli rd, rs1, shamt` | rd = rs1 >> shamt, logical |
| `SRAI` | `0x16` | `IS` | `srai rd, rs1, shamt` | rd = rs1 >> shamt, arithmetic |
| `SLTI` | `0x17` | `I` | `slti rd, rs1, imm16` | rd = (signed)rs1 < (signed)sign_extend(imm16) ? 1 else 0 |
| `SLTIU` | `0x18` | `I` | `sltiu rd, rs1, imm16` | rd = rs1 < sign_extend(imm16) ? 1 else 0, unsigned |
| `LI` | `0x19` | `I` | `li rd, imm16` | rd = zero_extend(imm16) |
| `LUI` | `0x1A` | `I` | `lui rd, imm16` | rd = zero_extend(imm16) << 16 |
| `LB` | `0x20` | `M` | `lb rd, offset(rs1)` | rd = sign_extend(byte at rs1 + sign_extend(imm16)) |
| `LH` | `0x21` | `M` | `lh rd, offset(rs1)` | rd = sign_extend(halfword at rs1 + sign_extend(imm16)) |
| `LW` | `0x22` | `M` | `lw rd, offset(rs1)` | rd = word at rs1 + sign_extend(imm16) |
| `LBU` | `0x23` | `M` | `lbu rd, offset(rs1)` | rd = zero_extend(byte at rs1 + sign_extend(imm16)) |
| `LHU` | `0x24` | `M` | `lhu rd, offset(rs1)` | rd = zero_extend(halfword at rs1 + sign_extend(imm16)) |
| `SB` | `0x28` | `M` | `sb rd, offset(rs1)` | byte at rs1 + sign_extend(imm16) = rd[7:0] |
| `SH` | `0x29` | `M` | `sh rd, offset(rs1)` | halfword at rs1 + sign_extend(imm16) = rd[15:0] |
| `SW` | `0x2A` | `M` | `sw rd, offset(rs1)` | word at rs1 + sign_extend(imm16) = rd |
| `BEQ` | `0x30` | `B` | `beq rs1, rs2, target` | if rs1 == rs2 then pc = pc + imm16 |
| `BNE` | `0x31` | `B` | `bne rs1, rs2, target` | if rs1 != rs2 then pc = pc + imm16 |
| `BLT` | `0x32` | `B` | `blt rs1, rs2, target` | if (signed)rs1 < (signed)rs2 then pc = pc + imm16 |
| `BGE` | `0x33` | `B` | `bge rs1, rs2, target` | if (signed)rs1 >= (signed)rs2 then pc = pc + imm16 |
| `BLTU` | `0x34` | `B` | `bltu rs1, rs2, target` | if rs1 < rs2 then pc = pc + imm16, unsigned |
| `BGEU` | `0x35` | `B` | `bgeu rs1, rs2, target` | if rs1 >= rs2 then pc = pc + imm16, unsigned |
| `JMP` | `0x38` | `J` | `jmp target` | pc = pc + imm20 |
| `CALL` | `0x39` | `J` | `call rd, target` | rd = pc + 1; pc = pc + imm20 |
| `JR` | `0x3B` | `R` | `jr rs1` | pc = rs1 |
| `WAITABS` | `0x40` | `I` | `waitabs rs1` | stall this context until the global cycle counter is >= rs1. The other context continues to issue on its own slots. |
| `WAITREL` | `0x41` | `I` | `waitrel rs1` | stall this context until the global cycle counter is >= the cycle in which this instruction issued plus rs1. |
| `WAITPIN` | `0x42` | `R` | `waitpin rs1, rs2` | stall this context until any pin selected by the mask in rs1 records an edge, or until the cycle counter is >= rs2 when rs2 is non-zero. Edge status remains readable in PIN_EDGE and is cleared by writing one to it. |
| `NOP` | `0x50` | `SYS` | `nop` | do nothing for one slot |
| `HALT` | `0x51` | `SYS` | `halt` | stop issuing this context; the other context keeps running |

## Pseudo-instructions

| Alias | Operands | Expands to |
| --- | --- | --- |
| `MOV` | 2 | `ADD {0}, {1}, r0` |
| `NEG` | 2 | `SUB {0}, r0, {1}` |
| `SEQZ` | 2 | `SLTIU {0}, {1}, 1` |
| `SNEZ` | 2 | `SLTU {0}, r0, {1}` |
| `BEQZ` | 2 | `BEQ {0}, r0, {1}` |
| `BNEZ` | 2 | `BNE {0}, r0, {1}` |
| `J` | 1 | `JMP {0}` |
| `RET` | 0 | `JR r15` |
| `LI32` | 2 | `LUI {0}, ((({1}) >> 16) & 0xFFFF)` ; `ORI {0}, {0}, (({1}) & 0xFFFF)` |

## Memory map

| Region | Base | Size | Notes |
| --- | --- | --- | --- |
| Instruction | `0x00000000` | 512 words | writable only by the bootloader |
| Data | `0x00000000` | 2048 bytes | 512 words, provisional; final size follows the area report |
| I/O | `0x00008000` | 256 bytes | memory-mapped registers |

### I/O registers

| Name | Address | Access | Description |
| --- | --- | --- | --- |
| `CYCLE` | `0x00008000` | ro | free-running 32-bit cycle counter; wraps about every 86 s at 50 MHz |
| `PIN_IN` | `0x00008004` | ro | synchronised input levels, bit n = pin n |
| `PIN_OUT` | `0x00008008` | rw | output levels for output-capable pins |
| `PIN_DIR` | `0x0000800C` | rw | direction, 1 = output, for bidirectional pins |
| `PIN_SET` | `0x00008010` | wo | write 1 to drive a pin high |
| `PIN_CLR` | `0x00008014` | wo | write 1 to drive a pin low |
| `PIN_XOR` | `0x00008018` | wo | write 1 to toggle a pin |
| `PIN_EDGE` | `0x0000801C` | rw1c | sticky edge flags, one bit per input-capable pin; write 1 to clear |
| `CTX_ID` | `0x00008020` | ro | issuing context number, 0 or 1 |
| `BOOT_REQ` | `0x00008024` | wo | write 0x4A4E5553 to re-enter the UART bootloader |

## Pin map

| Pin | Source | Direction |
| --- | --- | --- |
| 0 | `ui_in[0]` | input |
| 1 | `ui_in[1]` | input |
| 2 | `ui_in[2]` | input |
| 3 | `ui_in[3]` | input |
| 4 | `ui_in[4]` | input |
| 5 | `ui_in[5]` | input |
| 6 | `ui_in[6]` | input |
| 7 | `ui_in[7]` | input |
| 8 | `uo_out[0]` | output |
| 9 | `uo_out[1]` | output |
| 10 | `uo_out[2]` | output |
| 11 | `uo_out[3]` | output |
| 12 | `uo_out[4]` | output |
| 13 | `uo_out[5]` | output |
| 14 | `uo_out[6]` | output |
| 15 | `uo_out[7]` | output |
| 16 | `uio[0]` | bidir |
| 17 | `uio[1]` | bidir |
| 18 | `uio[2]` | bidir |
| 19 | `uio[3]` | bidir |
| 20 | `uio[4]` | bidir |
| 21 | `uio[5]` | bidir |
| 22 | `uio[6]` | bidir |
| 23 | `uio[7]` | bidir |

## Boot protocol

On reset the bootloader listens on pins 16 and 17 (`uio[0]` and `uio[1]`) for a little-endian image introduced by the magic value `0x4A414E5553`.

The bootloader listens at a fixed baud, loads an image into instruction memory, checks it, sets both context PCs from the image header and releases the core.

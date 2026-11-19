; hello.s - write 0..9 to data memory and halt.
;
; Expected: words at 0x100..0x127 contain 0..9 (little-endian).

        .org 0
start:  LI    r1, 0
        LI    r2, 10
        LI    r3, 0x100
loop:   SW    r1, 0(r3)
        ADDI  r1, r1, 1
        ADDI  r3, r3, 4
        BNE   r1, r2, loop
        HALT

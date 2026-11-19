; two_contexts.s - run two independent timed loops.
;
; Context 0 toggles pin 8 (uo_out[0]) every 20 cycles.
; Context 1 toggles pin 9 (uo_out[1]) every 30 cycles.
;
; Both loops run in the single image; the loader starts context 1 at the
; `ctx1` label.

        .equ IO_BASE,  0x8000
        .equ PIN_XOR,  0x18
        .equ PIN8,     0x0100
        .equ PIN9,     0x0200

        .org 0
ctx0:   LI32  r1, IO_BASE
        LI32  r2, PIN8
        LI    r3, 16
loop0:  SW    r2, PIN_XOR(r1)
        WAITREL r3
        JMP   loop0

ctx1:   LI32  r1, IO_BASE
        LI32  r2, PIN9
        LI    r3, 26
loop1:  SW    r2, PIN_XOR(r1)
        WAITREL r3
        JMP   loop1

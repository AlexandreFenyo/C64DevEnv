; world_tile(x, y) : code de tile de la case (x, y) du monde ; 0 hors du monde
; (x >= WORLD_W ou y >= WORLD_H). Pour les collisions, les bords...
; __fastcall__ : y dans A, x (16 bits) sur la pile C.

        .include "world_defs.inc"

        .export _world_tile
        .import world_seek, world_next, world_x, world_y, _world_cell_code
        .import incsp2
        .importzp sp

.proc _world_tile
        cmp #WORLD_H
        bcs outside
        sta world_y
        ldy #1
        lda (sp),y
        cmp #>WORLD_W           ; x < WORLD_W ?
        bcc inside
        bne outside
        dey
        lda (sp),y
        cmp #<WORLD_W
        bcs outside
inside: ldy #0
        lda (sp),y
        sta world_x
        iny
        lda (sp),y
        sta world_x+1
        jsr world_seek
        jsr world_next
        tax
        lda _world_cell_code,x
        ldx #0
        jmp incsp2
outside:
        lda #0
        ldx #0
        jmp incsp2
.endproc

; sprite_move(n, x, y) : position du sprite n. x sur 9 bits : 8 bits bas en
; $D000+2n, bit 9 dans le bit n de $D010 ; y en $D001+2n.
; Convention cc65 (__fastcall__) : y dans A ; x (2 octets) puis n (1 octet)
; sur la pile C : (sp)+0/1 = x, (sp)+2 = n ; on les retire (incsp3).

        .export _sprite_move
        .import incsp3
        .importzp sp, tmp1, tmp2

VIC_SPR0_X   = $D000
VIC_SPR0_Y   = $D001
VIC_SPR_HI_X = $D010

.proc _sprite_move
        sta tmp1                ; y
        ldy #2
        lda (sp),y              ; n
        sta tmp2
        asl
        tax                     ; X = 2n : registres X/Y du sprite n
        lda tmp1
        sta VIC_SPR0_Y,x
        ldy #0
        lda (sp),y              ; x, octet bas
        sta VIC_SPR0_X,x
        iny
        lda (sp),y              ; x, octet haut : seul le bit 0 compte
        ldx tmp2
        lsr                     ; bit 0 -> retenue
        lda VIC_SPR_HI_X
        bcc clear
        ora bits,x
        bne store               ; toujours (résultat non nul)
clear:  and masks,x
store:  sta VIC_SPR_HI_X
        jmp incsp3
.endproc

.segment "RODATA"
bits:   .byte $01, $02, $04, $08, $10, $20, $40, $80
masks:  .byte $FE, $FD, $FB, $F7, $EF, $DF, $BF, $7F

; world_copy2(n) : copie n octets de _wc_src1 vers _wc_dst1 ET de _wc_src2
; vers _wc_dst2 (écran et couleurs de la vue, même décalage), sans
; recouvrement. Boucle par pages, code automodifiant, ~21 cycles par paire
; d'octets. Sert à décaler la vue d'une case (world_scroll.c).
; __fastcall__ : n dans A/X.

        .export _world_copy2, _wc_src1, _wc_dst1, _wc_src2, _wc_dst2

        .segment "BSS"

_wc_src1:   .res 2
_wc_dst1:   .res 2
_wc_src2:   .res 2
_wc_dst2:   .res 2
cnt_lo:     .res 1

        .segment "CODE"

.proc _world_copy2
        sta cnt_lo
        lda _wc_src1
        sta ld1+1
        sta ldt1+1
        lda _wc_src1+1
        sta ld1+2
        sta ldt1+2
        lda _wc_dst1
        sta st1+1
        sta stt1+1
        lda _wc_dst1+1
        sta st1+2
        sta stt1+2
        lda _wc_src2
        sta ld2+1
        sta ldt2+1
        lda _wc_src2+1
        sta ld2+2
        sta ldt2+2
        lda _wc_dst2
        sta st2+1
        sta stt2+1
        lda _wc_dst2+1
        sta st2+2
        sta stt2+2
        ldy #0
        txa                     ; pages entières
        beq tail
        tax
page:
ld1:    lda $FFFF,y
st1:    sta $FFFF,y
ld2:    lda $FFFF,y
st2:    sta $FFFF,y
        iny
        bne page
        inc ld1+2
        inc st1+2
        inc ld2+2
        inc st2+2
        inc ldt1+2
        inc stt1+2
        inc ldt2+2
        inc stt2+2
        dex
        bne page
tail:   cpy cnt_lo
        beq done
ldt1:   lda $FFFF,y
stt1:   sta $FFFF,y
ldt2:   lda $FFFF,y
stt2:   sta $FFFF,y
        iny
        bne tail
done:   rts
.endproc

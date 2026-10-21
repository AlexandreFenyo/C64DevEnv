; rnd8() : nombre pseudo-aléatoire 1-255, registre à décalage à rétroaction
; linéaire (Galois, polynôme $B8 : période maximale 255). Graine en DATA.

        .export _rnd8

.proc _rnd8
        lda seed
        lsr
        bcc :+
        eor #$B8
:       sta seed
        ldx #0
        rts
.endproc

.segment "DATA"
seed:   .byte $A5

; wait_frame() : attend le début de la ligne raster 250 (bas de l'écran
; visible), donc une fois par image : 50 Hz en PAL. On attend d'abord d'en
; sortir, au cas où on y serait déjà.

        .export _wait_frame

RASTER  = $D012
LINE    = 250

.proc _wait_frame
@out:   lda RASTER
        cmp #LINE
        beq @out
@in:    lda RASTER
        cmp #LINE
        bne @in
        rts
.endproc

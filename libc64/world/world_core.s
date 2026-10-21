; world_core.s - décodeur du monde (libc64/world), utilisé par world_draw et
; world_tile. Format : voir tools/mkworld.py (littéraux < WORLD_NV,
; répétitions >= WORLD_NV, un segment tous les WORLD_SEG colonnes).
;
; world_seek : positionne le décodeur sur la case (world_x, world_y) ;
;              world_x <= WORLD_W-1, world_y <= WORLD_H-1 (non vérifié).
; world_next : A = index de valeur de la case courante, puis passe à la
;              suivante sur la ligne. Préserve Y (X est modifié).
; État : ptr1 (page zéro du runtime cc65, libre pendant un appel), rep, val.

        .include "world_defs.inc"

        .export world_seek, world_seek_segment, world_next, world_x, world_y
        .import world_seglo_lo, world_seglo_hi, world_seghi_lo, world_seghi_hi
        .importzp ptr1, ptr4

        .segment "BSS"

world_x:    .res 2              ; colonne demandée (0-WORLD_W-1)
world_y:    .res 1              ; ligne demandée
rep:        .res 1              ; répétitions restantes de val
val:        .res 1
skip:       .res 1

        .segment "CODE"

; world_seek_segment : ptr1 = début du segment contenant (world_x, world_y),
; A = nombre de cases à sauter dans ce segment pour atteindre world_x.
.proc world_seek_segment
        ; segment k = world_x / WORLD_SEG, skip = reste (soustractions : k <= 9)
        lda world_x
        ldx world_x+1
        ldy #0
div:    cpx #0
        bne sub
        cmp #WORLD_SEG
        bcc done
sub:    sec
        sbc #WORLD_SEG
        bcs :+
        dex
:       iny
        bne div                 ; toujours (y <= 10)
done:   sta skip
        ; ptr1 = adresse du segment y de la ligne world_y
        lda world_seglo_lo,y
        sta ptr4
        lda world_seglo_hi,y
        sta ptr4+1
        ldx world_seghi_lo,y
        lda world_seghi_hi,y
        ldy world_y
        pha
        lda (ptr4),y
        sta ptr1
        stx ptr4
        pla
        sta ptr4+1
        lda (ptr4),y
        sta ptr1+1
        lda skip
        rts
.endproc

.proc world_seek
        jsr world_seek_segment
        ldy #0
        sty rep
        tay                     ; on saute les cases avant world_x
        beq out
skipl:  jsr world_next
        dey
        bne skipl
out:    rts
.endproc

.proc world_next
        lda rep
        beq read
        dec rep
        lda val
        rts
read:   ldx #0
        lda (ptr1,x)
        inc ptr1
        bne :+
        inc ptr1+1
:       cmp #WORLD_NV
        bcs repeat
        sta val
        rts
repeat: sbc #WORLD_NV-1         ; retenue à 1 : répétitions restantes = octet - NV + 1
        sta rep
        lda val
        rts
.endproc

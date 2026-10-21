; world_core.s - décodeur du monde (libc64/world), utilisé par world_draw et
; world_tile. Format : voir tools/mkworld.py (littéraux < WORLD_NV,
; répétitions >= WORLD_NV, un segment tous les WORLD_SEG colonnes ; jetons
; codés en quartets : world_nib.inc, dont l'état est défini ici).
;
; world_seek : positionne le décodeur sur la case (world_x, world_y) ;
;              world_x <= WORLD_W-1, world_y <= WORLD_H-1 (non vérifié).
; world_next : A = index de valeur de la case courante, puis passe à la
;              suivante sur la ligne. Préserve Y (X est modifié).
; État : ptr1 (page zéro du runtime cc65, libre pendant un appel), rep, val.

        .include "world_defs.inc"
WORLD_NIB_STATE = 1                     ; l'état des quartets est défini ici
        .include "world_nib.inc"

        .export world_seek, world_seek_segment, world_next, world_x, world_y
        .export world_nib_half, world_nib_pend, world_nib_tmp, world_seg_next
        .import world_seglo_lo, world_seglo_hi, world_seghi_lo, world_seghi_hi
        .importzp ptr1, ptr4

        .segment "BSS"

world_x:    .res 2              ; colonne demandée (0-WORLD_W-1)
world_y:    .res 1              ; ligne demandée
rep:        .res 1              ; répétitions restantes de val
val:        .res 1
skip:       .res 1
world_seg_k: .res 1             ; segment courant (0-WORLD_NSEG-1)
segleft:    .res 1              ; cases restant dans ce segment (world_next)
world_nib_half: .res 1          ; 1 : quartet bas de world_nib_pend à lire
world_nib_pend: .res 1
world_nib_tmp:  .res 1

        .segment "CODE"

; world_seek_segment : ptr1 = début du segment contenant (world_x, world_y),
; A = nombre de cases à sauter dans ce segment pour atteindre world_x ;
; world_nib_half = 0, world_seg_k = numéro du segment.
.proc world_seek_segment
        ; segment k = world_x / WORLD_SEG, skip = reste (soustractions : k < WORLD_NSEG)
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
        bne div                 ; toujours (y <= WORLD_NSEG)
done:   sta skip
        sty world_seg_k
        jsr seg_ptr
        lda skip
        rts
.endproc

; world_seg_next : ptr1 = segment suivant de la même ligne (world_seg_k + 1,
; world_y), world_nib_half = 0. Les segments d'une ligne ne se suivent pas
; en mémoire (segments identiques partagés, alignés sur un octet) : un
; décodeur qui lit plusieurs cases d'une ligne l'appelle tous les WORLD_SEG
; cases. Préserve Y.
.proc world_seg_next
        tya
        pha
        inc world_seg_k
        ldy world_seg_k
        jsr seg_ptr
        pla
        tay
        rts
.endproc

; Y = numéro de segment -> ptr1 = adresse du segment de la ligne world_y,
; world_nib_half = 0. Utilise ptr4, X.
.proc seg_ptr
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
        lda #0
        sta world_nib_half
        rts
.endproc

.proc world_seek
        jsr world_seek_segment
        ldy #0
        sty rep
        ldy #WORLD_SEG
        sty segleft
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
        dec segleft
        lda val
        rts
read:   lda segleft             ; fin du segment : le suivant
        bne :+
        jsr world_seg_next
        lda #WORLD_SEG
        sta segleft
:       dec segleft
        NIB_TOKEN
        cmp #WORLD_NV
        bcs repeat
        sta val
        rts
repeat: sbc #WORLD_NV-1         ; retenue à 1 : répétitions restantes = jeton - NV + 1
        sta rep
        lda val
        rts
.endproc

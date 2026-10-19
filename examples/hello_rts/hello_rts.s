; hello_rts.s - variante de hello qui rend la main au BASIC (rts) : après
; l'affichage, le prompt READY. revient et le clavier répond. Pratique pour
; make run ; les tests de point d'arrêt utilisent examples/hello (boucle).

.include "c64.inc"

CHROUT          = $FFD2
CLRSCR          = $E544
WITNESS_ADDR    = $02FF
WITNESS_VALUE   = $42

        .segment "CODE"

start:
        jsr CLRSCR
        lda #$05                ; bordure verte
        sta VIC_BORDERCOLOR
        lda #$00                ; fond noir
        sta VIC_BG_COLOR0
        lda #$01                ; texte blanc
        sta $0286

        ldx #$00
print:
        lda message,x
        beq done
        jsr CHROUT
        inx
        bne print
done:
        lda #WITNESS_VALUE
        sta WITNESS_ADDR
        rts                     ; retour au BASIC : READY.

        .segment "RODATA"

message:
        .byte "hello from ca65!", $0D, "c64 dev env ready.", $0D, $0D, 0

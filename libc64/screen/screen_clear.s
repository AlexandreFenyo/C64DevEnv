; screen_clear(color) : écran texte $0400-$07E7 rempli d'espaces, mémoire
; couleur $D800-$DBE7 remplie avec la couleur. 1000 octets = 4 x 250 : on
; n'écrit pas au-delà, les pointeurs de sprites ($07F8-$07FF) sont préservés.

        .export _screen_clear

SCREEN  = $0400
COLORS  = $D800

.proc _screen_clear
        ldx #250
loop:   sta COLORS-1,x
        sta COLORS+249,x
        sta COLORS+499,x
        sta COLORS+749,x
        dex
        bne loop
        lda #$20                ; espace (code écran)
        ldx #250
loop2:  sta SCREEN-1,x
        sta SCREEN+249,x
        sta SCREEN+499,x
        sta SCREEN+749,x
        dex
        bne loop2
        rts
.endproc

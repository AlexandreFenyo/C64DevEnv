; world_color_copy(src) : copie 1000 octets de couleurs vers la Color RAM
; ($D800), dans l'ordre de l'écran (haut vers bas). Appelée en début de
; balayage vertical (ligne 250) lors d'un échange d'écrans : ~13 000 cycles,
; elle reste en avance sur le faisceau, qui affiche la ligne de caractères k
; vers la ligne raster 51 + 8k de l'image suivante.
; __fastcall__ : src dans A/X. Code automodifiant (octet haut des STA).

        .export _world_color_copy
        .importzp ptr1

COLORS = $D800

.proc _world_color_copy
        sta ptr1
        stx ptr1+1
        lda #>COLORS
        sta dest0+2
        sta dest1+2
        ldy #0                  ; 3 pages entières (2 octets par tour) puis 232 octets
        ldx #3
page:   lda (ptr1),y
dest0:  sta COLORS,y
        iny
        lda (ptr1),y
dest1:  sta COLORS,y
        iny
        bne page
        inc ptr1+1
        inc dest0+2
        inc dest1+2
        dex
        bne page
last:   lda (ptr1),y
        sta COLORS+768,y
        iny
        cpy #232
        bne last
        rts
.endproc

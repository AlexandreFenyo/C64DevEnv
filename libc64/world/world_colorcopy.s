; world_color_copy(src) : copie les WORLD_SCROLL_ROWS * 40 (640) octets de
; couleurs de la vue qui défile vers la Color RAM ($D800), dans l'ordre de
; l'écran (haut vers bas) ; les lignes du panneau, dessous, ne changent pas.
; Appelée en début de balayage vertical (ligne 250) lors d'un échange
; d'écrans : ~9 000 cycles,
; elle reste en avance sur le faisceau, qui affiche la ligne de caractères k
; vers la ligne raster 51 + 8k de l'image suivante.
; __fastcall__ : src dans A/X. Code automodifiant (octet haut des STA).

        .include "libc64_defs.inc"

        .export _world_color_copy
        .importzp ptr1

COLORS = $D800

.proc _world_color_copy
        sta ptr1
        stx ptr1+1
        lda #>COLORS
        sta dest0+2
        sta dest1+2
NBYTES = WORLD_SCROLL_ROWS * 40
.assert NBYTES .mod 256 <> 0, error, "world_color_copy : reste de page nul non prévu"

        ldy #0                  ; pages entières (2 octets par tour) puis le reste
        ldx #NBYTES / 256
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
        sta COLORS + (NBYTES & $FF00),y
        iny
        cpy #<NBYTES
        bne last
        rts
.endproc

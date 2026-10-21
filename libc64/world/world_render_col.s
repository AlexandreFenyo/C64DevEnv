; world_render_col(col) : décode la colonne col (0-39) de la vue qui défile
; (40 x WORLD_SCROLL_ROWS cases) dont
; le coin haut gauche est la case (_wr_tx, _wr_ty), dans _wr_screen et
; _wr_colors (mêmes variables que world_render_rows). Cases hors du monde :
; FILL_*. Segment et rang dans le segment calculés une fois pour la colonne
; (même colonne du monde sur toutes les lignes), puis par ligne : adresse du
; segment dans la table, saut des cases précédentes : par octet entier (2
; jetons) tant qu'ils précèdent la case voulue (tables world_nib_cells2 et
; world_nib_lastlit), une répétition d'un coup, jeton par jeton à la fin.
; __fastcall__ : col dans A.

        .include "world_defs.inc"
        .include "libc64_defs.inc"
        .include "world_nib.inc"
        .import world_nib_cells2, world_nib_lastlit

        .export _world_render_col
        .import world_seglo_lo, world_seglo_hi, world_seghi_lo, world_seghi_hi
        .import _world_cell_code, _world_cell_color
        .import _wr_tx, _wr_ty, _wr_screen, _wr_colors
        .importzp ptr1, ptr2, ptr3

FILL_CODE  = $4D
FILL_COLOR = 5

        .segment "BSS"

row:        .res 1              ; ligne de la vue
wy:         .res 1              ; ligne du monde
skip:       .res 1              ; rang de la colonne dans son segment
runlen:     .res 1
left:       .res 1              ; cases restant avant la case voulue
val:        .res 1
wxl:        .res 1              ; colonne du monde
wxh:        .res 1

        .segment "CODE"

.proc _world_render_col
        tay                     ; ptr2/ptr3 = haut de la colonne
        clc
        adc _wr_screen
        sta ptr2
        lda _wr_screen+1
        adc #0
        sta ptr2+1
        tya
        clc
        adc _wr_colors
        sta ptr3
        lda _wr_colors+1
        adc #0
        sta ptr3+1
        tya
        clc
        adc _wr_tx
        sta wxl
        lda _wr_tx+1
        adc #0
        sta wxh
        lda _wr_ty
        sta wy
        lda #0
        sta row
        lda wxh                 ; colonne hors du monde : tout en remplissage
        cmp #>WORLD_W
        bcc inside
        bne fillcol
        lda wxl
        cmp #<WORLD_W
        bcc inside
fillcol:
        lda #WORLD_H
        sta wy
        jmp rloop
inside: ; segment k = colonne / WORLD_SEG, skip = reste (k < WORLD_NSEG)
        lda wxl
        ldx wxh
        ldy #0
div:    cpx #0
        bne sub
        cmp #WORLD_SEG
        bcc divok
sub:    sec
        sbc #WORLD_SEG
        bcs :+
        dex
:       iny
        bne div
divok:  sta skip
        lda world_seglo_lo,y    ; tables d'adresses du segment k (indexées par ligne)
        sta tablo+1
        lda world_seglo_hi,y
        sta tablo+2
        lda world_seghi_lo,y
        sta tabhi+1
        lda world_seghi_hi,y
        sta tabhi+2

rloop:  ldy wy
        cpy #WORLD_H
        bcc :+
        jmp fill
:
tablo:  lda $FFFF,y
        sta ptr1
tabhi:  lda $FFFF,y
        sta ptr1+1
        lda #0
        sta world_nib_half      ; un segment commence sur un octet entier
        tay                     ; Y = position dans le segment
        NIB_TOKEN Y             ; un segment commence par un littéral
        sta val
        lda skip                ; cases restant avant la case voulue
        bne :+
        jmp emit
:
        sta left
cell:   lda world_nib_half      ; sur un octet entier : saut rapide possible
        bne slow
fast:   lda (ptr1),y            ; 2 jetons d'un coup, s'ils précèdent la case voulue
        tax
        lda world_nib_cells2,x  ; leurs cases (0 : échappement)
        beq slow
        cmp left
        bcs slow                ; l'octet atteint la case voulue : jeton par jeton
        eor #$FF                ; left -= cases (C = 0 : -cases - 1 + 1)
        sec
        adc left
        sta left
        lda world_nib_lastlit,x
        cmp #$FF
        beq :+
        sta val                 ; dernier littéral de l'octet
:       iny
        bne fast                ; toujours (segment < 256 octets)
slow:   NIB_TOKEN Y
        cmp #WORLD_NV
        bcs token
        sta val                 ; littéral : une case
        dec left
        beq emit
        jmp cell
token:  sbc #WORLD_NV-2         ; répétition de k cases (C = 1) : sautées d'un coup
        sta runlen
        lda left
        sec
        sbc runlen
        beq emit                ; la case voulue est dans la répétition
        bcc emit
        sta left
        jmp cell
emit:   ldx val
        ldy #0
        lda _world_cell_code,x
        sta (ptr2),y
        lda _world_cell_color,x
        sta (ptr3),y
        jmp next
fill:   ldy #0
        lda #FILL_CODE
        sta (ptr2),y
        lda #FILL_COLOR
        sta (ptr3),y
next:   inc wy                  ; (au-delà de WORLD_H : reste en remplissage)
        lda ptr2                ; ligne suivante (+40)
        clc
        adc #40
        sta ptr2
        bcc :+
        inc ptr2+1
:       lda ptr3
        clc
        adc #40
        sta ptr3
        bcc :+
        inc ptr3+1
:       inc row
        lda row
        cmp #WORLD_SCROLL_ROWS
        beq :+
        jmp rloop
:       rts
.endproc

; world_render_col(col) : décode la colonne col (0-39) de la vue 40x25 dont
; le coin haut gauche est la case (_wr_tx, _wr_ty), dans _wr_screen et
; _wr_colors (mêmes variables que world_render_rows). Cases hors du monde :
; FILL_*. Segment et rang dans le segment calculés une fois pour la colonne
; (même colonne du monde sur les 25 lignes), puis par ligne : adresse du
; segment dans la table, saut des cases précédentes, une répétition d'un
; coup (~250 cycles par ligne).
; __fastcall__ : col dans A.

        .include "world_defs.inc"

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
inside: ; segment k = colonne / WORLD_SEG, skip = reste (k <= 9)
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
        bcs fill
tablo:  lda $FFFF,y
        sta ptr1
tabhi:  lda $FFFF,y
        sta ptr1+1
        ldy #0
        lda (ptr1),y            ; un segment commence par un littéral
        sta val
        iny
        ldx skip                ; X = cases restant avant la case voulue
        beq emit
cell:   lda (ptr1),y
        iny
        cmp #WORLD_NV
        bcs token
        sta val                 ; littéral : une case
        dex
        bne cell
        beq emit
token:  sbc #WORLD_NV-2         ; répétition de k cases (C = 1) : sautées d'un coup
        sta runlen
        txa
        sec
        sbc runlen
        beq emit                ; la case voulue est dans la répétition
        bcc emit
        tax
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
        cmp #25
        beq :+
        jmp rloop
:       rts
.endproc

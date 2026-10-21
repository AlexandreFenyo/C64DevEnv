; world_render_rows(row0, n) : décode les lignes row0..row0+n-1 de la vue
; 40x25 dont le coin haut gauche est la case (_wr_tx, _wr_ty) du monde, dans
; un écran (_wr_screen) et un tampon de couleurs (_wr_colors) quelconques.
; Les cases hors du monde (colonnes >= WORLD_W, lignes >= WORLD_H : jamais
; visibles avec le défilement fin, voir world_scroll.c) reçoivent FILL_*.
; Sert au défilement : la vue suivante se prépare une ligne à la fois.
; Décodage en ligne (pas d'appel par case), source et destinations par code
; automodifiant. __fastcall__ : n dans A, row0 sur la pile C.

        .include "world_defs.inc"
        .include "world_nib.inc"

        .export _world_render_rows, _wr_tx, _wr_ty, _wr_screen, _wr_colors
        .import world_seek_segment, world_seg_next, world_x, world_y, _world_cell_code, _world_cell_color
        .import incsp1
        .importzp sp, ptr1

FILL_CODE  = $4D                ; TILE_VIDE (herbe unie), couleur par défaut 5
FILL_COLOR = 5

        .segment "BSS"

_wr_tx:     .res 2
_wr_ty:     .res 1
_wr_screen: .res 2
_wr_colors: .res 2
count:      .res 1
row:        .res 1
ncols:      .res 1              ; colonnes dans le monde (40 au plus)
skipcnt:    .res 1
rep:        .res 1
segleft:    .res 1              ; cases restant dans le segment courant
val:        .res 1

        .segment "CODE"

.proc _world_render_rows
        sta count
        ldy #0
        lda (sp),y
        sta row
        ; ncols = min(40, WORLD_W - tx)
        lda #<WORLD_W
        sec
        sbc _wr_tx
        tax
        lda #>WORLD_W
        sbc _wr_tx+1
        bne full                ; >= 256
        cpx #40
        bcc :+
full:   ldx #40
:       stx ncols
        lda count
        bne rloop
        jmp done

rloop:  ; adresses de la ligne row dans l'écran et le tampon (code automodifiant)
        lda row
        asl
        tax
        lda mul40,x
        clc
        adc _wr_screen
        sta scr+1
        sta scrf+1
        lda mul40+1,x
        adc _wr_screen+1
        sta scr+2
        sta scrf+2
        lda mul40,x
        clc
        adc _wr_colors
        sta col+1
        sta colf+1
        lda mul40+1,x
        adc _wr_colors+1
        sta col+2
        sta colf+2
        ldy #0
        lda _wr_ty
        clc
        adc row
        cmp #WORLD_H
        bcc inworld
        jmp fillrow             ; ligne hors du monde
inworld:
        sta world_y
        lda _wr_tx
        sta world_x
        lda _wr_tx+1
        sta world_x+1
        jsr world_seek_segment  ; ptr1 = segment, A = cases à sauter
        sta skipcnt
        lda #0
        sta rep
        lda #WORLD_SEG
        sta segleft
        ldy #0
cell:   lda rep
        beq :+
        jmp fromrep
:       lda segleft             ; fin du segment : le suivant (pas contigu en mémoire)
        bne :+
        jsr world_seg_next      ; préserve Y
        lda #WORLD_SEG
        sta segleft
:       NIB_TOKEN               ; jeton suivant (préserve Y)
        cmp #WORLD_NV
        bcs token
        sta val                 ; littéral
        jmp got
token:  sbc #WORLD_NV-1         ; retenue à 1 : répétitions restantes (>= 1)
        sta rep
        jmp got
fromrep:
        dec rep
got:    dec segleft
        lda skipcnt
        beq emit
        dec skipcnt
        jmp cell
emit:   ldx val
        lda _world_cell_code,x
scr:    sta $FFFF,y
        lda _world_cell_color,x
col:    sta $FFFF,y
        iny
        cpy ncols
        beq fillrow
        jmp cell
fillrow:
        cpy #40
        beq next
        lda #FILL_CODE
scrf:   sta $FFFF,y
        lda #FILL_COLOR
colf:   sta $FFFF,y
        iny
        bne fillrow
next:   inc row
        dec count
        beq done
        jmp rloop
done:   jmp incsp1

        .segment "RODATA"
mul40:
        .repeat 25, i
        .word i * 40
        .endrepeat
.endproc

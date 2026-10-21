; world_draw(x, y) : affiche la fenêtre 40x25 du monde dont le coin haut gauche
; est la case (x, y) : codes dans l'écran TILESET_SCREEN ($C000), couleurs
; dans la Color RAM. x et y sont ramenés dans [0, WORLD_MAX_X] et
; [0, WORLD_MAX_Y] : la fenêtre reste dans le monde.
; __fastcall__ : y dans A, x (16 bits) sur la pile C.
; Durée : environ 3 images (décodage de ~60 cases par ligne).

        .include "world_defs.inc"

        .export _world_draw
        .import world_seek, world_next, world_x, world_y, _world_cell_code, _world_cell_color
        .import incsp2
        .importzp sp, ptr2, ptr3

SCREEN = $C000
COLORS = $D800

        .segment "BSS"

row:    .res 1
y0:     .res 1

        .segment "CODE"

.proc _world_draw
        cmp #WORLD_MAX_Y+1
        bcc :+
        lda #WORLD_MAX_Y
:       sta y0
        ldy #1
        lda (sp),y              ; x, octet haut
        tax
        dey
        lda (sp),y              ; x, octet bas
        cpx #>(WORLD_MAX_X+1)   ; x > WORLD_MAX_X ?
        bcc xok
        bne xclamp
        cmp #<(WORLD_MAX_X+1)
        bcc xok
xclamp: lda #<WORLD_MAX_X
        ldx #>WORLD_MAX_X
xok:    sta xlo
        stx xhi
        lda #<SCREEN
        sta ptr2
        lda #>SCREEN
        sta ptr2+1
        lda #<COLORS
        sta ptr3
        lda #>COLORS
        sta ptr3+1
        lda #0
        sta row
rloop:  lda xlo
        sta world_x
        lda xhi
        sta world_x+1
        lda y0
        clc
        adc row
        sta world_y
        jsr world_seek
        ldy #0
cloop:  jsr world_next          ; préserve Y
        tax
        lda _world_cell_code,x
        sta (ptr2),y
        lda _world_cell_color,x
        sta (ptr3),y
        iny
        cpy #40
        bne cloop
        lda ptr2                ; ligne d'écran suivante
        clc
        adc #40
        sta ptr2
        sta ptr3
        bcc :+
        inc ptr2+1
        inc ptr3+1
:       inc row
        lda row
        cmp #25
        bne rloop
        jmp incsp2

        .segment "BSS"
xlo:    .res 1
xhi:    .res 1
.endproc

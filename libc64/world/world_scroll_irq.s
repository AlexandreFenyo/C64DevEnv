; world_scroll_irq.s - handler raster du défilement fin (world_scroll.c) et
; état partagé avec world_scroll_work. En assembleur : il tourne à chaque
; image (~400 cycles, contre ~2 900 en C).
;
; À chaque image :
;   1. plan : vitesse effective et axes du prochain franchissement de case.
;      En diagonale, si l'axe en retard peut franchir sa case dans la même
;      image que l'autre en allant d'un pixel plus vite, il le fait :
;      deux franchissements rapprochés laisseraient trop peu de temps pour
;      préparer la vue intermédiaire ;
;   2. nouvelle position, bornée au monde (world_scroll_bumps compte les
;      chocs) ;
;   3. même case : décalage fin seulement. Nouvelle case : si la vue
;      préparée est celle-là, bascule d'écran ($D018), décalage fin, copie
;      des couleurs dans la Color RAM (en avance sur le faisceau) ; sinon la
;      position attend (world_scroll_stalls) ;
;   4. plan depuis la nouvelle position : la case visée devient la vue à
;      préparer (étape remise à 0, génération incrémentée) si elle change.

        .include "world_defs.inc"

        .export _world_scroll_irq, _ws_apply_fine
        .export _world_px, _world_py, _world_scroll_dx, _world_scroll_dy
        .export _world_scroll_stalls, _world_scroll_frames, _world_scroll_bumps, _world_scroll_front
        .export _ws_cur_tx, _ws_cur_ty, _ws_back_tx, _ws_back_ty, _ws_back_step, _ws_gen
        .export _ws_front_colors, _ws_back_colors
        .import _world_color_copy
        .importzp tmp1, tmp2

MAX_PX    = WORLD_W * 8 - 304   ; = WORLD_SCROLL_MAX_PX (libc64.h)
MAX_PY    = WORLD_H * 8 - 192
MAX_TX    = MAX_PX >> 3         ; case de la colonne 0 au plus
MAX_TY    = MAX_PY >> 3
STEP_DONE = 3                   ; étapes de world_scroll_work (world_scroll.c)

VIC_CTRL1 = $D011
VIC_CTRL2 = $D016
VIC_ADDR  = $D018

        .segment "DATA"

_ws_back_tx:      .word $FFFF   ; vue en préparation ($FFFF : aucune)
_ws_front_colors: .word colors_a        ; reflet de la Color RAM
_ws_back_colors:  .word colors_b        ; couleurs de la vue en préparation

        .segment "BSS"

_world_px:           .res 2     ; coin haut gauche visible, en pixels
_world_py:           .res 2
_world_scroll_dx:    .res 1     ; vitesse voulue (signée), pixels par image
_world_scroll_dy:    .res 1
_world_scroll_stalls: .res 2
_world_scroll_frames: .res 2
_world_scroll_bumps: .res 1
_world_scroll_front: .res 1     ; 0 : écran $C000 affiché, 1 : $C400
_ws_cur_tx:          .res 2     ; case de la colonne 0 de l'écran affiché
_ws_cur_ty:          .res 1
_ws_back_ty:         .res 1
_ws_back_step:       .res 1
_ws_gen:             .res 1
colors_a:            .res 1000
colors_b:            .res 1000
edx:    .res 1                  ; résultat de plan
edy:    .res 1
mx:     .res 1                  ; 1 : l'axe fait partie du prochain franchissement
my:     .res 1
rx:     .res 1                  ; pixels avant la case suivante
ry:     .res 1
sx:     .res 1                  ; |vitesse|
sy:     .res 1
fx:     .res 1                  ; images avant franchissement
fy:     .res 1
nx:     .res 2                  ; position candidate
ny:     .res 2
ntx:    .res 2                  ; sa case
nty:    .res 1
ptx:    .res 2                  ; case visée
pty:    .res 1

        .segment "CODE"

.proc _world_scroll_irq
        inc _world_scroll_frames
        bne :+
        inc _world_scroll_frames+1
:       jsr plan

        ; nx = px + edx, borné à [0, MAX_PX]
        ldx #0
        lda edx
        bpl :+
        dex
:       clc
        adc _world_px
        sta nx
        txa
        adc _world_px+1
        sta nx+1
        bmi xlow
        lda nx
        cmp #<(MAX_PX + 1)
        lda nx+1
        sbc #>(MAX_PX + 1)
        bcc xok
        lda #<MAX_PX
        sta nx
        lda #>MAX_PX
        sta nx+1
        inc _world_scroll_bumps
        jmp xok
xlow:   lda #0
        sta nx
        sta nx+1
        inc _world_scroll_bumps
xok:
        ; ny = py + edy, borné à [0, MAX_PY]
        ldx #0
        lda edy
        bpl :+
        dex
:       clc
        adc _world_py
        sta ny
        txa
        adc _world_py+1
        sta ny+1
        bmi ylow
        lda ny
        cmp #<(MAX_PY + 1)
        lda ny+1
        sbc #>(MAX_PY + 1)
        bcc yok
        lda #<MAX_PY
        sta ny
        lda #>MAX_PY
        sta ny+1
        inc _world_scroll_bumps
        jmp yok
ylow:   lda #0
        sta ny
        sta ny+1
        inc _world_scroll_bumps
yok:
        ; case de la position candidate
        lda nx+1
        sta ntx+1
        lda nx
        lsr ntx+1
        ror a
        lsr ntx+1
        ror a
        lsr ntx+1
        ror a
        sta ntx
        lda ny+1
        sta tmp1
        lda ny
        lsr tmp1
        ror a
        lsr tmp1
        ror a
        lsr tmp1
        ror a
        sta nty

        lda ntx
        cmp _ws_cur_tx
        bne cross
        lda ntx+1
        cmp _ws_cur_tx+1
        bne cross
        lda nty
        cmp _ws_cur_ty
        bne cross
        jsr setpos              ; même case
        jmp predict

cross:  lda _ws_back_step       ; la vue préparée est-elle celle-là ?
        cmp #STEP_DONE
        bne stall
        lda _ws_back_tx
        cmp ntx
        bne stall
        lda _ws_back_tx+1
        cmp ntx+1
        bne stall
        lda _ws_back_ty
        cmp nty
        bne stall
        lda _world_scroll_front ; bascule (balayage vertical)
        eor #1
        sta _world_scroll_front
        beq :+
        lda #$12                ; écran $C400, motifs $C800
        bne :++
:       lda #$02                ; écran $C000, motifs $C800
:       sta VIC_ADDR
        jsr setpos
        lda _ws_back_colors
        ldx _ws_back_colors+1
        jsr _world_color_copy
        ldx _ws_front_colors    ; échange des tampons de couleurs
        ldy _ws_front_colors+1
        lda _ws_back_colors
        sta _ws_front_colors
        lda _ws_back_colors+1
        sta _ws_front_colors+1
        stx _ws_back_colors
        sty _ws_back_colors+1
        lda ntx
        sta _ws_cur_tx
        lda ntx+1
        sta _ws_cur_tx+1
        lda nty
        sta _ws_cur_ty
        lda #$FF
        sta _ws_back_tx
        sta _ws_back_tx+1
        jmp predict

stall:  inc _world_scroll_stalls        ; la position attend
        bne predict
        inc _world_scroll_stalls+1

predict:
        jsr plan
        lda _ws_cur_tx
        sta ptx
        lda _ws_cur_tx+1
        sta ptx+1
        lda _ws_cur_ty
        sta pty
        lda mx
        beq py_
        lda edx
        bmi xdec
        inc ptx
        bne xchk
        inc ptx+1
        jmp xchk
xdec:   lda ptx
        bne :+
        dec ptx+1
:       dec ptx
xchk:   lda #<MAX_TX            ; au-delà du bord (ou sous 0 : $FFFF) : pas de case
        cmp ptx
        lda #>MAX_TX
        sbc ptx+1
        bcs py_
        lda _ws_cur_tx
        sta ptx
        lda _ws_cur_tx+1
        sta ptx+1
py_:    lda my
        beq pcmp
        lda edy
        bmi ydec
        inc pty
        jmp ychk
ydec:   dec pty
ychk:   lda #MAX_TY
        cmp pty
        bcs pcmp
        lda _ws_cur_ty
        sta pty
pcmp:   lda ptx                 ; case visée = case affichée : rien à préparer
        cmp _ws_cur_tx
        bne diff
        lda ptx+1
        cmp _ws_cur_tx+1
        bne diff
        lda pty
        cmp _ws_cur_ty
        beq done
diff:   lda ptx                 ; déjà en préparation
        cmp _ws_back_tx
        bne set
        lda ptx+1
        cmp _ws_back_tx+1
        bne set
        lda pty
        cmp _ws_back_ty
        beq done
set:    lda ptx
        sta _ws_back_tx
        lda ptx+1
        sta _ws_back_tx+1
        lda pty
        sta _ws_back_ty
        lda #0
        sta _ws_back_step
        inc _ws_gen
done:   rts
.endproc

; plan : depuis (world_px, world_py) et la vitesse voulue, edx/edy (vitesse
; effective de cette image) et mx/my (axes du prochain franchissement).
.proc plan
        lda _world_scroll_dx
        sta edx
        lda _world_scroll_dy
        sta edy
        lda #0
        sta mx
        sta my
        ldy edx
        beq nox
        lda _world_px
        jsr tocross
        sta rx
        tya
        jsr absa
        sta sx
        sta tmp2
        lda rx
        jsr cdiv
        sta fx
        inc mx
nox:    ldy edy
        beq noy
        lda _world_py
        jsr tocross
        sta ry
        tya
        jsr absa
        sta sy
        sta tmp2
        lda ry
        jsr cdiv
        sta fy
        inc my
noy:    lda mx
        and my
        beq done                ; un seul axe (ou aucun)
        lda fx
        cmp fy
        beq done                ; même image : les deux
        bcs ylead
        ; x d'abord (fx < fy) : y peut-il franchir dans fx images ?
        sta tmp2
        lda ry
        jsr cdiv                ; vitesse nécessaire = ceil(ry / fx)
        ldx sy
        inx
        stx tmp2
        cmp tmp2
        beq :+
        bcs xonly
:       ldy edy                 ; edy = signe(dy) * nécessaire
        bpl :+
        eor #$FF
        clc
        adc #1
:       sta edy
        rts
xonly:  lda #0
        sta my
        rts
ylead:  lda fy                  ; y d'abord : symétrique
        sta tmp2
        lda rx
        jsr cdiv
        ldx sx
        inx
        stx tmp2
        cmp tmp2
        beq :+
        bcs yonly
:       ldy edx
        bpl :+
        eor #$FF
        clc
        adc #1
:       sta edx
        rts
yonly:  lda #0
        sta mx
done:   rts
.endproc

; A = octet bas d'une position, Y = vitesse (non nulle) -> A = pixels avant
; de changer de case dans ce sens (1-8). Préserve Y.
.proc tocross
        and #7
        cpy #$80
        bcs neg
        eor #7                  ; 8 - (p & 7)
        clc
        adc #1
        rts
neg:    clc                     ; (p & 7) + 1
        adc #1
        rts
.endproc

; A = |A| (signé).
.proc absa
        cmp #$80
        bcc :+
        eor #$FF
        adc #0                  ; retenue à 1 : + 1
:       rts
.endproc

; A = ceil(A / tmp2), A > 0, tmp2 > 0. Utilise X.
.proc cdiv
        ldx #0
        sec
loop:   inx
        sbc tmp2
        beq :+
        bcs loop
:       txa
        rts
.endproc

; Position = candidate, puis décalage fin.
.proc setpos
        lda nx
        sta _world_px
        lda nx+1
        sta _world_px+1
        lda ny
        sta _world_py
        lda ny+1
        sta _world_py+1
.endproc
        ; continue dans _ws_apply_fine

; void ws_apply_fine(void) : $D016/$D011 selon (world_px, world_py), en 38
; colonnes et 24 lignes ; bit 7 de $D011 (comparaison raster) à 0.
.proc _ws_apply_fine
        lda _world_px
        and #7
        eor #7
        sta tmp1
        lda VIC_CTRL2
        and #$F0
        ora tmp1
        sta VIC_CTRL2
        lda _world_py
        and #7
        eor #7
        sta tmp1
        lda VIC_CTRL1
        and #$70
        ora tmp1
        sta VIC_CTRL1
        rts
.endproc

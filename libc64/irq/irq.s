; irq.s - répartiteur d'interruptions IRQ avec table fixe de handlers.
;
; Le KERNAL entre dans toute IRQ par $FF48 (A, X, Y empilés) puis saute via
; le vecteur $0314 : on le remplace par `dispatch`. Selon la source :
;   - VIC-II ($D019 bit 7) : acquittement, appel des handlers IRQ_SRC_VIC,
;     puis fin d'interruption par la routine du KERNAL $EA81 (dépile Y X A, RTI) ;
;   - sinon CIA 1 (timer du KERNAL, 60 Hz) : acquittement du CIA, CLI, appel
;     des handlers IRQ_SRC_CIA, puis l'ancien vecteur (KERNAL $EA31 : clavier,
;     horloge). Après le CLI, tout ce traitement (plusieurs centaines de
;     cycles) est interruptible par le VIC-II : une IRQ raster reste à l'heure
;     même quand elle tombe pendant l'IRQ du KERNAL. Une IRQ VIC-II peut donc
;     s'imbriquer dans une IRQ CIA : chaque source a sa propre zone de
;     sauvegarde et ses propres variables de parcours.
; Avant d'appeler les handlers, les registres de page zéro du runtime cc65
; (sp, sreg, regsave, ptr1-4, tmp1-4) sont sauvegardés : un handler peut
; être écrit en C et le programme interrompu n'en voit rien.
; Les appels indirects passent par des trampolines « JMP absolu » en RAM et
; non par JMP (vecteur) : ce dernier se trompe d'octet haut quand le vecteur
; chevauche une frontière de page ($xxFF), bug du 6502 (ld65 le signale).
; Les modifications de la table se font sous SEI (php/sei/plp : l'état I
; d'origine est rendu, y compris quand on est appelé depuis un handler).

        .include "libc64_defs.inc"

        .export _irq_init, _irq_done, _irq_register, _irq_unregister, _irq_vic_flags
        .import incsp2
        .importzp sp, sreg, regsave, ptr1, ptr2, ptr3, ptr4, tmp1, tmp2, tmp3, tmp4

IRQ_VECTOR  = $0314
VIC_IRQ     = $D019
VIC_IRQMASK = $D01A
KERNAL_RTI  = $EA81             ; pla tay pla tax pla rti
CIA1_ICR    = $DC0D

        .segment "BSS"

h_lo:           .res IRQ_MAX_HANDLERS
h_hi:           .res IRQ_MAX_HANDLERS   ; 0 = emplacement libre
h_src:          .res IRQ_MAX_HANDLERS
old_jmp:        .res 3          ; JMP vers l'ancien vecteur IRQ (KERNAL)
old_vector      = old_jmp+1
installed:      .res 1
vic_idx:        .res 1          ; état du parcours, par source
vic_jmp:        .res 3          ; JMP vers le handler en cours
vic_zp:         .res 20
cia_idx:        .res 1
cia_jmp:        .res 3
cia_zp:         .res 20
_irq_vic_flags: .res 1

        .segment "CODE"

; void irq_init(void) : installe le répartiteur (une seule fois).
.proc _irq_init
        lda installed
        bne done
        php
        sei
        lda #$4C                ; opcode JMP absolu des trampolines
        sta old_jmp
        sta vic_jmp
        sta cia_jmp
        lda IRQ_VECTOR
        sta old_vector
        lda IRQ_VECTOR+1
        sta old_vector+1
        lda #<dispatch
        sta IRQ_VECTOR
        lda #>dispatch
        sta IRQ_VECTOR+1
        lda #1
        sta installed
        plp
done:   rts
.endproc

; void irq_done(void) : vecteur d'origine, IRQ du VIC-II coupées.
.proc _irq_done
        lda installed
        beq done
        php
        sei
        lda old_vector
        sta IRQ_VECTOR
        lda old_vector+1
        sta IRQ_VECTOR+1
        lda #0
        sta VIC_IRQMASK
        sta installed
        lda #$FF
        sta VIC_IRQ             ; acquitte ce qui serait en attente
        plp
done:   rts
.endproc

; unsigned char irq_register(irq_handler_t h, unsigned char sources)
; __fastcall__ : sources dans A, h sur la pile C ((sp)+0/1).
.proc _irq_register
        sta tmp1                ; sources
        jsr _irq_init
        ldy #0
        lda (sp),y
        sta tmp2                ; h, octet bas
        iny
        lda (sp),y
        sta tmp3                ; h, octet haut
        php
        sei
        ldx #0                  ; déjà enregistré ?
find:   lda h_lo,x
        cmp tmp2
        bne next
        lda h_hi,x
        cmp tmp3
        beq store
next:   inx
        cpx #IRQ_MAX_HANDLERS
        bne find
        ldx #0                  ; sinon, premier emplacement libre
free:   lda h_hi,x
        beq store
        inx
        cpx #IRQ_MAX_HANDLERS
        bne free
        plp                     ; table pleine
        lda #$FF
        ldx #0
        jmp incsp2
store:  lda tmp1
        sta h_src,x
        lda tmp2
        sta h_lo,x
        lda tmp3
        sta h_hi,x              ; en dernier : l'emplacement devient actif
        stx tmp4
        plp
        lda tmp4
        ldx #0
        jmp incsp2
.endproc

; void irq_unregister(irq_handler_t h) : h dans A/X.
.proc _irq_unregister
        sta tmp2
        stx tmp3
        php
        sei
        ldx #0
loop:   lda h_lo,x
        cmp tmp2
        bne next
        lda h_hi,x
        cmp tmp3
        bne next
        lda #0
        sta h_hi,x
        sta h_src,x
next:   inx
        cpx #IRQ_MAX_HANDLERS
        bne loop
        plp
        rts
.endproc

; --- Répartiteur -----------------------------------------------------------
.proc dispatch
        cld
        lda VIC_IRQ
        bpl cia                 ; bit 7 : l'interruption vient du VIC-II
        sta _irq_vic_flags
        sta VIC_IRQ             ; acquittement (écrire 1 efface le bit)
        jsr call_vic            ; sous SEI : pas d'imbrication VIC dans VIC
        jmp KERNAL_RTI
cia:    lda CIA1_ICR            ; acquitte le CIA (sinon CLI ferait reboucler l'IRQ)
        cli                     ; le VIC-II peut maintenant interrompre
        jsr call_cia
        jmp old_jmp
.endproc

; Appelle les handlers de la source SRC ; IDX, VEC, ZP : état propre à la
; source (une IRQ VIC-II peut interrompre le parcours des handlers CIA).
.macro CALL_HANDLERS SRC, IDX, TRAMP, ZP
        .local any, anynext, found, loop, next
        ldx #0                  ; au moins un handler concerné ?
any:    lda h_hi,x
        beq anynext
        lda h_src,x
        and #SRC
        bne found
anynext:
        inx
        cpx #IRQ_MAX_HANDLERS
        bne any
        rts
found:  ; Sauvegarde de la page zéro du runtime cc65 (handlers en C).
        .repeat 2, i
        lda sp+i
        sta ZP+i
        lda sreg+i
        sta ZP+2+i
        .endrepeat
        .repeat 4, i
        lda regsave+i
        sta ZP+4+i
        .endrepeat
        .repeat 2, i
        lda ptr1+i
        sta ZP+8+i
        lda ptr2+i
        sta ZP+10+i
        lda ptr3+i
        sta ZP+12+i
        lda ptr4+i
        sta ZP+14+i
        .endrepeat
        lda tmp1
        sta ZP+16
        lda tmp2
        sta ZP+17
        lda tmp3
        sta ZP+18
        lda tmp4
        sta ZP+19

        ldx #0
loop:   stx IDX
        lda h_hi,x
        beq next
        lda h_src,x
        and #SRC
        beq next
        lda h_lo,x
        sta TRAMP+1
        lda h_hi,x
        sta TRAMP+2
        jsr TRAMP
next:   ldx IDX
        inx
        cpx #IRQ_MAX_HANDLERS
        bne loop

        .repeat 2, i
        lda ZP+i
        sta sp+i
        lda ZP+2+i
        sta sreg+i
        .endrepeat
        .repeat 4, i
        lda ZP+4+i
        sta regsave+i
        .endrepeat
        .repeat 2, i
        lda ZP+8+i
        sta ptr1+i
        lda ZP+10+i
        sta ptr2+i
        lda ZP+12+i
        sta ptr3+i
        lda ZP+14+i
        sta ptr4+i
        .endrepeat
        lda ZP+16
        sta tmp1
        lda ZP+17
        sta tmp2
        lda ZP+18
        sta tmp3
        lda ZP+19
        sta tmp4
        rts
.endmacro

.proc call_vic
        CALL_HANDLERS IRQ_SRC_VIC, vic_idx, vic_jmp, vic_zp
.endproc

.proc call_cia
        CALL_HANDLERS IRQ_SRC_CIA, cia_idx, cia_jmp, cia_zp
.endproc

; raster.s - handlers appelés à une ligne raster donnée, table fixe.
;
; S'appuie sur irq : `dispatch` est enregistré comme handler IRQ_SRC_VIC.
;
; Précision : l'IRQ raster est demandée RASTER_LEAD lignes avant la ligne
; voulue ; à l'interruption, on attend la ligne exacte puis on appelle ses
; handlers. Le délai variable d'entrée (KERNAL, répartiteur, sauvegarde de la
; page zéro) est ainsi absorbé : le handler démarre au début de sa ligne à
; quelques cycles près.
;
; Rapidité : la table est tenue TRIÉE par ligne (n entrées contiguës), à
; l'enregistrement. Pendant l'interruption, on avance simplement d'une entrée
; à la suivante : quelques dizaines de cycles entre deux handlers, ce qui
; permet des lignes très proches (3 lignes d'écart pour une bande de
; couleur). Si la suivante est trop proche pour une nouvelle IRQ, on l'attend
; sur place ; sinon on reprogramme l'IRQ ; après la dernière, retour à la
; première, à l'image suivante.
;
; Un handler peut appeler raster_register / raster_unregister (se déplacer,
; se retirer) : la table est réordonnée et la position resynchronisée. Coût :
; quelques lignes raster ; laisser de la marge avant le handler suivant.

        .include "libc64_defs.inc"

        .export _raster_register, _raster_unregister
        .import _irq_register, _irq_vic_flags, pushax, incsp2
        .importzp sp, tmp1, tmp2, tmp3, tmp4

VIC_CTRL1   = $D011             ; bit 7 = bit 8 de la ligne raster
VIC_RASTER  = $D012
VIC_IRQ     = $D019
VIC_IRQMASK = $D01A

        .segment "BSS"

h_lo:        .res RASTER_MAX_HANDLERS   ; entrées 0..count-1, triées par ligne
h_hi:        .res RASTER_MAX_HANDLERS
l_lo:        .res RASTER_MAX_HANDLERS
l_hi:        .res RASTER_MAX_HANDLERS
count:       .res 1
pos:         .res 1             ; prochaine entrée à servir
target_lo:   .res 1             ; sa ligne
target_hi:   .res 1
hooked:      .res 1
in_dispatch: .res 1
dirty:       .res 1             ; table modifiée par un handler
cur_hi:      .res 1
call_jmp:    .res 3             ; JMP absolu vers le handler (pas de JMP indirect : bug $xxFF)

        .segment "CODE"

; Enregistre `dispatch` auprès d'irq (une fois).
.proc hook
        lda hooked
        bne done
        lda #<dispatch
        ldx #>dispatch
        jsr pushax
        lda #IRQ_SRC_VIC
        jsr _irq_register
        lda #$4C                ; opcode JMP absolu du trampoline
        sta call_jmp
        lda #1
        sta hooked
done:   rts
.endproc

; Retire de la table le handler tmp1/tmp2 s'il y est (décalage à gauche).
.proc remove
        ldx #0
find:   cpx count
        beq done
        lda h_lo,x
        cmp tmp1
        bne next
        lda h_hi,x
        cmp tmp2
        beq found
next:   inx
        bne find
found:  dec count
shift:  cpx count
        beq done
        lda h_lo+1,x
        sta h_lo,x
        lda h_hi+1,x
        sta h_hi,x
        lda l_lo+1,x
        sta l_lo,x
        lda l_hi+1,x
        sta l_hi,x
        inx
        bne shift
done:   rts
.endproc

; unsigned char raster_register(unsigned int line, irq_handler_t h)
; __fastcall__ : h dans A/X, line sur la pile C ((sp)+0/1).
; Renvoie 0, ou 0xFF si la table est pleine.
.proc _raster_register
        pha
        txa
        pha
        jsr hook                ; utilise tmp1-4 et la pile C : avant tout le reste
        pla
        sta tmp2                ; h, octet haut
        pla
        sta tmp1                ; h, octet bas
        ldy #0
        lda (sp),y
        sta tmp3                ; ligne, octet bas
        iny
        lda (sp),y
        sta tmp4                ; ligne, octet haut
        bne lineok              ; ligne >= 256 : forcément >= RASTER_LEAD
        lda tmp3
        cmp #RASTER_LEAD
        bcs lineok
        lda #RASTER_LEAD        ; plus tôt : impossible d'anticiper, on ramène
        sta tmp3
lineok: php
        sei
        jsr remove              ; déjà enregistré : on le replace
        lda count
        cmp #RASTER_MAX_HANDLERS
        bcc room
        plp                     ; table pleine
        lda #$FF
        ldx #0
        jmp incsp2
room:   ; Insertion triée : on décale vers la droite les lignes > nouvelle.
        ldx count
ins:    beq put
        lda tmp3                ; nouvelle - ligne(x-1) : retenue = nouvelle >= ligne
        cmp l_lo-1,x
        lda tmp4
        sbc l_hi-1,x
        bcs put
        lda h_lo-1,x
        sta h_lo,x
        lda h_hi-1,x
        sta h_hi,x
        lda l_lo-1,x
        sta l_lo,x
        lda l_hi-1,x
        sta l_hi,x
        dex
        jmp ins
put:    lda tmp1
        sta h_lo,x
        lda tmp2
        sta h_hi,x
        lda tmp3
        sta l_lo,x
        lda tmp4
        sta l_hi,x
        inc count
        jsr changed
        plp
        lda #0
        tax
        jmp incsp2
.endproc

; void raster_unregister(irq_handler_t h) : h dans A/X.
.proc _raster_unregister
        sta tmp1
        stx tmp2
        php
        sei
        jsr remove
        jsr changed
        plp
        rts
.endproc

; La table a changé (sous SEI). Depuis un handler : `dispatch` resynchronise.
; Depuis le programme : on repart de la première ligne.
.proc changed
        lda in_dispatch
        beq prog
        lda #1
        sta dirty
        rts
prog:   lda #0
        sta pos
        lda count
        beq off
        jsr set_target
        lda #$01
        sta VIC_IRQ             ; efface un éventuel ancien déclenchement raster
        lda VIC_IRQMASK
        ora #$01                ; IRQ raster activée
        sta VIC_IRQMASK
        rts
off:    lda VIC_IRQMASK
        and #$FE                ; plus de handler : IRQ raster coupée
        sta VIC_IRQMASK
        rts
.endproc

; target = ligne de l'entrée pos ; IRQ demandée à target - RASTER_LEAD.
.proc set_target
        ldx pos
        lda l_lo,x
        sta target_lo
        sec
        sbc #RASTER_LEAD
        sta VIC_RASTER
        lda l_hi,x
        sta target_hi
        sbc #0
        lsr                     ; bit 0 (bit 8 de la ligne) -> retenue
        lda VIC_CTRL1
        and #$7F
        bcc :+
        ora #$80
:       sta VIC_CTRL1
        rts
.endproc

; Handler IRQ_SRC_VIC (registres de page zéro déjà sauvegardés par irq).
; Chemin le plus court possible entre deux handlers (lignes proches) : un seul
; calcul de l'écart à la ligne voulue, puis appel, attente ou nouvelle IRQ.
.proc dispatch
        lda _irq_vic_flags
        and #$01                ; interruption raster ?
        bne go
        rts
go:     lda #1
        sta in_dispatch
        lda pos
        cmp count
        bcc load
        lda #0                  ; table raccourcie entre-temps
        sta pos
        lda count
        bne load
        jmp off

load:   ldx pos                 ; target = ligne de l'entrée pos
        lda l_lo,x
        sta target_lo
        lda l_hi,x
        sta target_hi
        ; écart = target - ligne courante
        lda VIC_CTRL1
        asl                     ; bit 8 de la ligne -> retenue
        lda #0
        rol
        sta cur_hi
        lda target_lo
        sec
        sbc VIC_RASTER
        tax
        lda target_hi
        sbc cur_hi
        bmi call                ; déjà dépassée : tout de suite
        beq near
far:    jmp later               ; 256 lignes ou plus, ou assez loin : IRQ
near:   cpx #0
        beq call                ; atteinte
        cpx #RASTER_LEAD+2
        bcs far                 ; assez loin pour une nouvelle IRQ
        ; Attente de la ligne exacte (bit 8 d'abord s'il doit changer).
        lda target_hi
        cmp cur_hi
        beq lo
        lda target_hi
        beq hb0
hb1:    bit VIC_CTRL1
        bpl hb1
        bmi lo
hb0:    bit VIC_CTRL1
        bmi hb0
lo:     lda target_lo
wait:   cmp VIC_RASTER
        bne wait

call:   ; Tous les handlers de cette ligne (consécutifs : table triée).
        ldx pos
        lda h_lo,x
        sta call_jmp+1
        lda h_hi,x
        sta call_jmp+2
        jsr call_jmp
        lda dirty
        bne resync
        inc pos
        ldx pos
        cpx count
        bcs wrap
        lda l_lo,x              ; même ligne ?
        cmp target_lo
        bne toload
        lda l_hi,x
        cmp target_hi
        beq call
toload: jmp load

resync: ; Table modifiée par le handler : première entrée de ligne > target.
        lda #0
        sta dirty
        ldx #0
rs:     cpx count
        bcs rsend
        lda target_lo           ; target - ligne : retenue = target >= ligne
        cmp l_lo,x
        lda target_hi
        sbc l_hi,x
        bcc rsend               ; ligne > target
        inx
        bne rs
rsend:  stx pos
        cpx count
        bcs wrap
        jmp load

later:  jsr set_target
        jmp done
wrap:   lda #0                  ; image suivante : première ligne de la table
        sta pos
        lda count
        beq off
        jsr set_target
        jmp done
off:    lda VIC_IRQMASK
        and #$FE
        sta VIC_IRQMASK
done:   lda #0
        sta in_dispatch
        rts
.endproc

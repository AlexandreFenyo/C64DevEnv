; sprite_sid.s - exemple à suivre pas à pas dans VS Code (F5 sur ce fichier).
;
; Chaque bloc a un effet visible dans un groupe « puces » du panneau
; Variables (Mémoire, VIC-II, Sprites, SID) : le commentaire du bloc dit
; quoi regarder. F10 avance d'une ligne, F11 entre dans un sous-programme.
;
; Déroulement : un sprite (petit vaisseau) apparaît, une note de 440 Hz est
; jouée sur la voix 1 du SID, puis le sprite traverse l'écran de gauche à
; droite, un pixel par image, synchronisé sur le balayage (raster). Après
; NOTE_FRAMES images, la note est relâchée. Retour au BASIC à la fin : le
; sprite reste affiché, RUN recommence.

.include "c64.inc"

SPRITE_DATA     = $0340         ; tampon cassette : bloc 13 ($0340 / 64)
SPRITE_PTR0     = $07F8         ; pointeurs de sprites = écran ($0400) + $3F8
X_START         = 24            ; bord gauche visible
X_END           = 280           ; au-delà de 255 : bit 9 dans VIC_SPR_HI_X
Y_POS           = 140
RASTER_LINE     = 250           ; ligne attendue à chaque image (bas de l'écran)
NOTE_FRAMES     = 100           ; durée de la note, en images (2 s en PAL)
FREQ_440HZ      = $1D45         ; 440 * 2^24 / 985248 (horloge PAL)
WITNESS_ADDR    = $02FF
WITNESS_VALUE   = $42

xpos            = $FB           ; position x sur 16 bits ($FB-$FC, libres en asm)
frames          = $FD           ; images écoulées depuis le début de la note

        .segment "CODE"

start:
        ; --- 1. Mémoire : $01 dit quelles ROM sont visibles. Groupe
        ; « Mémoire ($01, vecteurs) » : BASIC ROM, E/S en $D000, KERNAL ROM.
        lda $01                 ; on le lit seulement (valeur habituelle : $37)

        ; --- 2. Motif du sprite : 63 octets copiés en $0340. Survolez
        ; SPRITE_DATA, ou tapez « $0340,63 » dans les espions.
        ldx #62
copy:   lda ship,x
        sta SPRITE_DATA,x
        dex
        bpl copy

        ; --- 3. Sprite 0. Groupe « Sprites » : sprite 0 passe de « inactif »
        ; à sa position et sa couleur ; « pointeur » donne $0340.
        lda #SPRITE_DATA / 64
        sta SPRITE_PTR0
        lda #7                  ; jaune
        sta VIC_SPR0_COLOR
        lda #<X_START
        sta xpos
        lda #>X_START
        sta xpos+1
        jsr set_x
        lda #Y_POS
        sta VIC_SPR0_Y
        lda #%00000001          ; sprite 0 agrandi en largeur et en hauteur
        sta VIC_SPR_EXP_X
        sta VIC_SPR_EXP_Y
        sta VIC_SPR_ENA         ; activé : le vaisseau apparaît

        ; --- 4. Note sur la voix 1. Groupe « SID » : volume 15, puis
        ; ADSR, 440 Hz, et forme d'onde triangle avec le gate ouvert.
        lda #15
        sta SID_Amp             ; volume maximal, pas de filtre
        lda #$09                ; attaque 0 (2 ms), déclin 9 (750 ms)
        sta SID_AD1
        lda #$A8                ; maintien 10/15, relâchement 8 (300 ms)
        sta SID_SUR1
        lda #<FREQ_440HZ
        sta SID_S1Lo
        lda #>FREQ_440HZ
        sta SID_S1Hi
        lda #%00010001          ; triangle + gate : la note commence
        sta SID_Ctl1
        lda #0
        sta frames

        ; --- 5. Déplacement, une image à la fois. F10 sur « jsr wait_frame »
        ; laisse passer une image ; le groupe « VIC-II » montre alors la ligne
        ; raster 250. Surveillez x dans le groupe « Sprites » : après 255,
        ; le bit 0 de VIC_SPR_HI_X ($D010) prend le relais.
move:   jsr wait_frame
        inc xpos
        bne :+
        inc xpos+1
:       jsr set_x
        inc frames
        lda frames
        cmp #NOTE_FRAMES
        bne :+
        lda #%00010000          ; triangle, gate fermé : relâchement de la note
        sta SID_Ctl1
:       lda xpos+1              ; fin quand xpos = X_END
        cmp #>X_END
        bne move
        lda xpos
        cmp #<X_END
        bne move

        ; --- 6. Fin : témoin pour les tests, puis retour au BASIC.
        lda #WITNESS_VALUE
        sta WITNESS_ADDR
        rts

; Position x du sprite 0 sur 9 bits : 8 bits bas dans VIC_SPR0_X, bit 9
; dans le bit 0 de VIC_SPR_HI_X.
set_x:
        lda xpos
        sta VIC_SPR0_X
        lda VIC_SPR_HI_X
        and #%11111110
        ldy xpos+1
        beq :+
        ora #%00000001
:       sta VIC_SPR_HI_X
        rts

; Attend le début de la ligne RASTER_LINE : une fois par image (50 Hz).
; On attend d'abord d'en sortir, au cas où on y serait déjà.
wait_frame:
:       lda VIC_HLINE
        cmp #RASTER_LINE
        beq :-
:       lda VIC_HLINE
        cmp #RASTER_LINE
        bne :-
        rts

        .segment "RODATA"

; Vaisseau : 21 lignes de 24 pixels (3 octets par ligne).
ship:
        .byte %00000000, %00011000, %00000000
        .byte %00000000, %00111100, %00000000
        .byte %00000000, %01111110, %00000000
        .byte %00000000, %01100110, %00000000
        .byte %00000000, %11100111, %00000000
        .byte %00000001, %11111111, %10000000
        .byte %00000011, %11111111, %11000000
        .byte %00000111, %11011011, %11100000
        .byte %00001111, %11011011, %11110000
        .byte %00011111, %11111111, %11111000
        .byte %00111111, %11111111, %11111100
        .byte %01111111, %11111111, %11111110
        .byte %11111111, %11111111, %11111111
        .byte %11111100, %00111100, %00111111
        .byte %11111000, %00011000, %00011111
        .byte %11110000, %00011000, %00001111
        .byte %01100000, %00011000, %00000110
        .byte %00000000, %00111100, %00000000
        .byte %00000000, %01111110, %00000000
        .byte %00000000, %01100110, %00000000
        .byte %00000000, %01000010, %00000000

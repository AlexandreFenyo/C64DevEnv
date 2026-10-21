; panel_init(color) : panneau de texte en bas de l'écran, sous la vue qui
; défile (world_scroll), avec les caractères du système.
;
; Mémoire (banque VIC 3, $C000-$FFFF) : la ROM de caractères n'y est pas
; visible du VIC-II ; les motifs du panneau sont en RAM $E000-$E7FF (sous la
; ROM du KERNAL : le processeur y écrit, le VIC-II y lit). Seuls les
; caractères du texte y sont copiés de la ROM (jeu majuscules) : A-Z,
; chiffres, « : », espace, « = » (codes écran habituels) ; les 217 autres
; codes sont à zéro, réservés aux graphiques (panel_glyph). Écran du panneau
; en $F000 (lignes PANEL_ROW et suivantes) ; Color RAM des mêmes lignes à
; `color` (la vue qui défile n'écrit que les lignes au-dessus).
;
; Coupure de l'écran (lignes raster) :
;   48-175  vue qui défile : WORLD_SCROLL_ROWS lignes de caractères, décalage
;           vertical y = $D011 & 7 (0-7) ; ses lignes commencent en 48+y+8k ;
;           entre 48 et 175 il y en a exactement 16 pour tout y (128 lignes),
;           donc le compteur de lignes du VIC-II (VCBASE) arrive au panneau
;           toujours sur la ligne PANEL_ROW ;
;   176-183 bande noire (mode invalide ECM+BMM) : cache la fin de la
;           dernière ligne de la vue (y lignes) ;
;   184-246 panneau : YSCROLL = 0 (184 = ligne de caractère), 40 colonnes,
;           fond noir, écran $F000, motifs $E000.
; Handler 1 (ligne 174) : écriture A, $D011 = YSCROLL 6 (7 si y = 7) au
; milieu de la ligne 175 (invisible) : la ligne de caractères suivante tombe
; dans la bande (182 ou 183), après la fin de la dernière ligne de la vue ;
; écriture B, + ECM/BMM (noir) dans la bordure droite de 175 ou au tout début
; de 176. L'entrée du handler et les délais dépendent de y : la ligne 174
; (y = 6) ou 175 (y = 7) est une « bad line » qui bloque le processeur 40
; cycles : délais par table (split1_delay1/2), réglés par mesure.
; Handler 2 (ligne 182, jamais une bad line) : $D018, $D016, $D021 pendant la
; bande noire, puis $D011 = texte + YSCROLL 0 après la bad line 183 (le
; processeur, bloqué pendant celle-ci, repart au cycle 55) : le panneau
; commence en mode normal à la ligne 184.
; __fastcall__ : color dans A.

        .include "libc64_defs.inc"

        .export _panel_init, panel_split1, panel_split2
        .import _raster_register, pushax
        .importzp ptr1, ptr2

VIC_CTRL1 = $D011
VIC_CTRL2 = $D016
VIC_ADDR  = $D018
VIC_BG    = $D021
CHARSET   = $E000               ; motifs du panneau (2 Ko, 256 codes)
SCREEN    = $F000
COLORS    = $D800
LINE1     = 174
LINE2     = 182
PANEL_D018 = $C8                ; écran $F000 (12 x 1 Ko), motifs $E000 (4 x 2 Ko)
PANEL_BG  = 0                   ; noir

        .segment "CODE"

.proc _panel_init
        pha                     ; couleur du texte
        ; Motifs du panneau ($E000-$E7FF) : tout à zéro (codes libres pour
        ; les graphiques), puis les seuls caractères du texte, copiés de la
        ; ROM (jeu majuscules/graphiques, $D000) à leur code écran.
        ; $01 = $32 : ROM de caractères visible en $D000, KERNAL, pas de BASIC
        ; (le programme peut occuper $A000-$BFFF).
        lda #<CHARSET
        sta ptr2
        lda #>CHARSET
        sta ptr2+1
        lda #0
        tay
        ldx #8
clr:    sta (ptr2),y
        iny
        bne clr
        inc ptr2+1
        dex
        bne clr
        php
        sei
        lda $01
        pha
        lda #$32
        sta $01
        ldx #0
glyph:  lda text_codes,x        ; ptr1 = $D000 + code * 8, ptr2 = $E000 + code * 8
        sta ptr1
        lda #0
        sta ptr1+1
        asl ptr1
        rol ptr1+1
        asl ptr1
        rol ptr1+1
        asl ptr1
        rol ptr1+1
        lda ptr1
        sta ptr2
        lda ptr1+1
        ora #>CHARSET
        sta ptr2+1
        lda ptr1+1
        ora #>$D000
        sta ptr1+1
        ldy #7
:       lda (ptr1),y
        sta (ptr2),y
        dey
        bpl :-
        inx
        cpx #TEXT_CODES
        bne glyph
        pla
        sta $01
        plp
        ; Écran du panneau : espaces ; Color RAM des mêmes lignes : couleur.
        pla
        tax
        ldy #0
fill:   lda #32
        sta SCREEN + PANEL_ROW * 40,y
        sta SCREEN + PANEL_ROW * 40 + PANEL_ROWS * 40 - 256,y
        txa
        sta COLORS + PANEL_ROW * 40,y
        sta COLORS + PANEL_ROW * 40 + PANEL_ROWS * 40 - 256,y
        iny
        bne fill
        ; Handlers.
        lda #<LINE1
        ldx #>LINE1
        jsr pushax
        lda #<panel_split1
        ldx #>panel_split1
        jsr _raster_register
        lda #<LINE2
        ldx #>LINE2
        jsr pushax
        lda #<panel_split2
        ldx #>panel_split2
        jmp _raster_register
.endproc

; Ligne 174 : YSCROLL de la bande, puis noir à partir de la ligne 176.
.proc panel_split1
        lda VIC_CTRL1
        and #7
        tax
        ldy split1_delay1,x
:       dey
        bne :-
        lda split1_d011,x       ; mode texte, écran allumé, YSCROLL 6 (7 si y = 7)
        sta VIC_CTRL1           ; écriture A : ligne 175, cycles ~35-50 (invisible)
        ldy split1_delay2,x
:       dey
        bne :-
        ora #$60                ; + ECM + BMM : mode invalide, noir
        sta VIC_CTRL1           ; écriture B : bordure droite de 175 (cycles 55-63) ou début de 176
        rts
.endproc

; Ligne 182 : registres du panneau, puis mode texte juste avant la ligne 184.
.proc panel_split2
        lda #PANEL_D018
        sta VIC_ADDR
        lda #$08                ; 40 colonnes, pas de multicolore, XSCROLL 0
        sta VIC_CTRL2
        lda #PANEL_BG
        sta VIC_BG
        ldy #SPLIT2_DELAY
:       dey
        bne :-
        lda #$10                ; mode texte, écran allumé, 24 lignes, YSCROLL 0
        sta VIC_CTRL1           ; écriture : ligne 183 après la bad line (cycles 55-63)
        rts
.endproc

        .segment "RODATA"

; Codes écran copiés de la ROM : A-Z (1-26), espace (32), 0-9 et « : »
; (48-58), « = » (61). Les autres codes (217) sont libres : panel_glyph.
text_codes:
        .byte 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19
        .byte 20, 21, 22, 23, 24, 25, 26, 32, 48, 49, 50, 51, 52, 53, 54, 55, 56
        .byte 57, 58, 61
TEXT_CODES = * - text_codes

; Handler 1, réglé par mesure (tours de boucle de 5 cycles), selon y :
; - y = 0-5 : entrée vers 174/36 ; A vers 175/41, B vers 175/60 ;
; - y = 6 : 174 est une bad line, entrée vers 175/16 ; A tout de suite ;
; - y = 7 : 175 est une bad line (processeur arrêté de 12 à 55) : B est
;   lancé avant et s'achève vers 175/58 ; A (YSCROLL 7 inchangé) sans effet.
; YSCROLL 6 : bad line invisible en 182, après la fin de la dernière ligne de
; la vue (175 + y <= 181), sauf y = 7 (fin en 182) : YSCROLL 7, bad line en
; 183. L'écriture A doit précéder le cycle ~57 de la ligne 175 : si y = 0, la
; vue y finit (RC = 7) et un changement de YSCROLL plus tardif fait compter
; au VIC-II une ligne de caractères de trop (panneau décalé, constaté) ; B ne
; doit pas précéder le cycle 55 (fin de la ligne 175 coupée).
split1_delay1: .byte 10, 10, 10, 10, 10, 10, 1, 1
split1_delay2: .byte 2, 2, 2, 2, 2, 2, 3, 3
split1_d011:   .byte $16, $16, $16, $16, $16, $16, $16, $17
; Handler 2 : la ligne 183 est une bad line (YSCROLL 7) : le processeur s'y
; arrête du cycle 12 au cycle 55 ; l'écriture de $D011, prévue vers le
; cycle 18-22 sans blocage, a lieu vers 183/61-184/2 (fenêtre utile :
; 183/55 à 184/10, avant la bad line du panneau).
SPLIT2_DELAY = 5

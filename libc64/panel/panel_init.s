; panel_init(color) : panneau de texte en bas de l'écran, sous la vue qui
; défile (world_scroll), dans le jeu de caractères du système.
;
; Mémoire (banque VIC 3, $C000-$FFFF) : la ROM de caractères n'y est pas
; visible du VIC-II : ses 4 Ko sont copiés en RAM $E000-$EFFF (sous la ROM
; du KERNAL : le processeur y écrit, le VIC-II y lit) ; le panneau utilise le
; jeu minuscules/majuscules ($E800) et son propre écran en $F000 (lignes
; PANEL_ROW et suivantes). Color RAM : lignes PANEL_ROW.. à `color` (la vue
; qui défile n'écrit que les lignes au-dessus).
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
;           fond noir, écran $F000, motifs $E800.
; Handler 1 (ligne 174) : écrit $D011 = noir + YSCROLL 7 dans la bordure
; droite de la ligne 175 (cycles 55-63) : avant, la ligne 175 serait coupée ;
; après, la ligne 176 commencerait une nouvelle ligne de caractères si y = 0.
; YSCROLL 7 : une seule ligne de caractères (invisible) en 183 ; la ligne de
; la vue en cours s'achève avant ; à 184, le VIC-II reprend la ligne PANEL_ROW.
; L'entrée du handler et le délai dépendent de y : la ligne 174 (y = 6) ou
; 175 (y = 7) est une « bad line » qui bloque le processeur 40 cycles :
; délai par table (split1_delay), réglé par mesure.
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
CHARSET   = $E000               ; copie de la ROM (4 Ko : deux jeux)
SCREEN    = $F000
COLORS    = $D800
LINE1     = 174
LINE2     = 182
PANEL_D018 = $CA                ; écran $F000 (12 x 1 Ko), motifs $E800 (5 x 2 Ko)
PANEL_BG  = 0                   ; noir

        .segment "CODE"

.proc _panel_init
        pha                     ; couleur du texte
        ; Copie de la ROM de caractères ($D000-$DFFF) en RAM $E000-$EFFF :
        ; $01 = $32 : ROM de caractères visible en $D000, KERNAL, pas de BASIC
        ; (le programme peut occuper $A000-$BFFF).
        php
        sei
        lda $01
        pha
        lda #$32
        sta $01
        lda #<$D000
        sta ptr1
        lda #>$D000
        sta ptr1+1
        lda #<CHARSET
        sta ptr2
        lda #>CHARSET
        sta ptr2+1
        ldx #16
        ldy #0
copy:   lda (ptr1),y
        sta (ptr2),y
        iny
        bne copy
        inc ptr1+1
        inc ptr2+1
        dex
        bne copy
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

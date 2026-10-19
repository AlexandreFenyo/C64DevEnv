; hello.s - exemple ca65 : efface l'écran, affiche une chaîne, change la
; couleur de bordure, écrit une valeur témoin en $02FF puis boucle.
;
; Lié avec c64-asm.cfg et -u __EXEHDR__ : un en-tête BASIC "SYS 2061" est
; ajouté par cc65, le code commence en $080D.

.include "c64.inc"              ; VIC_BORDERCOLOR, VIC_BG_COLOR0, SCREEN_RAM...

CHROUT          = $FFD2         ; KERNAL : affiche un caractère PETSCII
CLRSCR          = $E544         ; KERNAL : efface l'écran (routine interne)
COLOR_RAM       = $D800
WITNESS_ADDR    = $02FF         ; adresse témoin lue par les tests
WITNESS_VALUE   = $42           ; valeur témoin attendue

        .segment "CODE"

start:
        jsr CLRSCR
        lda #$05                ; bordure verte
        sta VIC_BORDERCOLOR
        lda #$00                ; fond noir
        sta VIC_BG_COLOR0
        lda #$01                ; texte blanc : couleur courante du KERNAL
        sta $0286

        ldx #$00
print:
        lda message,x
        beq done
        jsr CHROUT
        inx
        bne print
done:
        lda #WITNESS_VALUE
        sta WITNESS_ADDR

loop:
        jmp loop                ; boucle infinie (point d'arrêt des tests)

        .segment "RODATA"

message:
        ; cc65 convertit ASCII -> PETSCII : les minuscules du source
        ; deviennent les majuscules du jeu de caractères par défaut du C64.
        .byte "hello from ca65!", $0D, "c64 dev env ready.", 0

; joy2_read() : manette du port 2, lue sur le port A du CIA 1 ($DC00).
; Les contacts sont actifs à 0 : on inverse pour rendre 1 = actionné.
; Bits : 0 haut, 1 bas, 2 gauche, 3 droite, 4 feu (constantes J_* de libc64.h).

        .export _joy2_read

CIA1_PRA = $DC00

.proc _joy2_read
        lda CIA1_PRA
        eor #$FF
        and #$1F
        ldx #0                  ; valeur de retour sur 16 bits pour cc65
        rts
.endproc

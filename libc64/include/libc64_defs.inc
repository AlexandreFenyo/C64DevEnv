; libc64_defs.inc - constantes de libc64 pour l'assembleur. Doivent rester
; égales aux #define de libc64.h (le test 6 le vérifie). Changer une taille de
; table : modifier les deux fichiers, puis make (la bibliothèque est recompilée).

IRQ_MAX_HANDLERS    = 4         ; taille fixe de la table de l'irq
IRQ_SRC_CIA         = $01       ; timer du CIA 1 (IRQ du KERNAL, 60 Hz)
IRQ_SRC_VIC         = $02       ; VIC-II (raster, collisions)
RASTER_MAX_HANDLERS = 4         ; taille fixe de la table de raster
RASTER_LEAD         = 8         ; l'interruption est demandée 8 lignes avant

J_UP    = $01
J_DOWN  = $02
J_LEFT  = $04
J_RIGHT = $08
J_FIRE  = $10

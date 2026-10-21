; libc64_defs.inc - constantes de libc64 pour l'assembleur. Doivent rester
; égales aux #define de libc64.h (le test 6 le vérifie). Changer une taille de
; table : modifier les deux fichiers, puis make (la bibliothèque est recompilée).

IRQ_MAX_HANDLERS    = 4         ; taille fixe de la table de l'irq
IRQ_SRC_CIA         = $01       ; timer du CIA 1 (IRQ du KERNAL, 60 Hz)
IRQ_SRC_VIC         = $02       ; VIC-II (raster, collisions)
RASTER_MAX_HANDLERS = 4         ; taille fixe de la table de raster
RASTER_LEAD         = 8         ; l'interruption est demandée 8 lignes avant

WORLD_SCROLL_ROWS   = 16        ; lignes de caractères de la vue qui défile (haut de l'écran)
WORLD_SCROLL_VIEW_H = 121       ; hauteur visible de cette vue, en pixels (lignes raster 55-175)
PANEL_ROW           = 16        ; 1re ligne de caractères du panneau (écran $F000)
PANEL_ROWS          = 8         ; lignes de texte du panneau

J_UP    = $01
J_DOWN  = $02
J_LEFT  = $04
J_RIGHT = $08
J_FIRE  = $10

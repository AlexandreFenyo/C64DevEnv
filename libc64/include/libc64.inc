; libc64.inc - bibliothèque libc64 depuis l'assembleur (ca65).
; Mêmes fonctions que libc64.h (noms précédés de « _ », convention cc65) :
; un argument unique d'un octet se passe dans A, un mot dans A (bas) / X (haut) ;
; les fonctions à plusieurs arguments attendent les premiers sur la pile C
; de cc65 : depuis l'asm, préférer celles à un seul argument.

.import _screen_clear, _screen_colors, _screen_print
.import _wait_frame
.import _sprite_load, _sprite_show, _sprite_hide, _sprite_move
.import _joy2_read
.import _sid_init, _sid_beep, _sid_release
.import _rnd8

J_UP    = $01
J_DOWN  = $02
J_LEFT  = $04
J_RIGHT = $08
J_FIRE  = $10

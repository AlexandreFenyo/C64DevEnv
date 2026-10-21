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
.import _irq_init, _irq_done, _irq_register, _irq_unregister, _irq_vic_flags
.import _raster_register, _raster_unregister

.include "libc64_defs.inc"

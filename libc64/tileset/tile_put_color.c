/* tile_put_color : pose un tile avec une Color RAM imposée (convention de la
   carte {tile, colorRam}) ; pour un tile multicolore, ajouter 8 (bit 3). */
#include "libc64.h"

void __fastcall__ tile_put_color(unsigned char x, unsigned char y, unsigned char code,
                                 unsigned char color)
{
    unsigned int offset = y * 40 + x;

    *((unsigned char *)TILESET_SCREEN + offset) = code;
    *((unsigned char *)0xD800 + offset) = color;
}

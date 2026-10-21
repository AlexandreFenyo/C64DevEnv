/* tile_put : pose un tile à la case (x, y) avec sa Color RAM par défaut. */
#include "libc64.h"
#include "tiles.h"

void __fastcall__ tile_put(unsigned char x, unsigned char y, unsigned char code)
{
    unsigned int offset = y * 40 + x;

    *((unsigned char *)TILESET_SCREEN + offset) = code;
    *((unsigned char *)0xD800 + offset) = tile_color(code);
}

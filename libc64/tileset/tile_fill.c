/* tile_fill : remplit tout l'écran d'un tile, avec sa Color RAM par défaut. */
#include <string.h>
#include "libc64.h"

void __fastcall__ tile_fill(unsigned char code)
{
    memset((void *)TILESET_SCREEN, code, 1000);
    memset((void *)0xD800, tile_color(code), 1000);
}

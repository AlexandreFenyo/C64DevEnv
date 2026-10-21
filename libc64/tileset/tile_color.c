/* tile_color : Color RAM par défaut d'un code (0 pour un code non défini). */
#include "libc64.h"
#include "tiles.h"

unsigned char __fastcall__ tile_color(unsigned char code)
{
    if (code < TILE_FIRST || code > TILE_LAST) {
        return 0;
    }
    return tileset_colors[code - TILE_FIRST];
}

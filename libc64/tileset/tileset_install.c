/* tileset_install : installe le jeu de caractères du tileset (libc64/tileset)
   en TILESET_CHARSET et règle le VIC-II comme le décrit tileset.txt :
   fond, couleurs multicolores partagées, mode multicolore.

   Le jeu de caractères doit être en RAM, dans la banque VIC courante (banque 0,
   $0000-$3FFF) et hors de $1000-$1FFF, où le VIC-II voit la ROM de
   caractères : $3800 est le dernier emplacement de 2 Ko de la banque. Le
   programme (code, données, BSS) doit donc s'arrêter avant : vérifié ici. */
#include <c64.h>
#include <string.h>
#include "libc64.h"
#include "tiles.h"

extern char _BSS_RUN__[], _BSS_SIZE__[];   /* fin du programme (éditeur de liens) */

unsigned char tileset_install(void)
{
    unsigned char *cs = (unsigned char *)TILESET_CHARSET;

    if ((unsigned)_BSS_RUN__ + (unsigned)_BSS_SIZE__ > TILESET_CHARSET) {
        return 0xFF;                            /* le programme déborde sur $3800 */
    }
    memset(cs, 0, TILE_FIRST * 8);              /* codes libres : vides */
    memcpy(cs + TILE_FIRST * 8, tileset_glyphs, (TILE_LAST - TILE_FIRST + 1) * 8);
    memset(cs + (TILE_LAST + 1) * 8, 0, (255 - TILE_LAST) * 8);
    VIC.bgcolor0 = TILESET_BG;
    VIC.bgcolor1 = TILESET_MC1;
    VIC.bgcolor2 = TILESET_MC2;
    VIC.ctrl2 |= 0x10;                          /* multicolore, case par case (bit 3 de la Color RAM) */
    /* $D018 : bits 1-3 = adresse du jeu de caractères / 2 Ko dans la banque. */
    VIC.addr = (VIC.addr & 0xF1) | ((TILESET_CHARSET >> 10) & 0x0E);
    return 0;
}

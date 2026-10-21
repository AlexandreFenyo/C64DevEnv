/* tileset_install : installe le jeu de caractères du tileset (libc64/tileset)
   en TILESET_CHARSET et règle le VIC-II comme le décrit tileset.txt :
   fond, couleurs multicolores partagées, mode multicolore.

   Banque VIC 3 ($C000-$FFFF) : écran $C000, jeu de caractères $C800 (pas de
   ROM de caractères vue par le VIC-II dans cette banque). Le programme, lié
   avec __HIMEM__ = $C000, s'arrête avant : laisse le monde (libc64/world) et
   le code utiliser $0801-$BFFF (la ROM BASIC est coupée par le runtime cc65). */
#include <c64.h>
#include <string.h>
#include "libc64.h"
#include "tiles.h"

extern char _BSS_RUN__[], _BSS_SIZE__[];   /* fin du programme (éditeur de liens) */

unsigned char tileset_install(void)
{
    unsigned char *cs = (unsigned char *)TILESET_CHARSET;

    if ((unsigned)_BSS_RUN__ + (unsigned)_BSS_SIZE__ > TILESET_SCREEN) {
        return 0xFF;                            /* le programme déborde sur $C000 */
    }
    memset(cs, 0, TILE_FIRST * 8);              /* codes libres : vides */
    memcpy(cs + TILE_FIRST * 8, tileset_glyphs, (TILE_LAST - TILE_FIRST + 1) * 8);
    memset(cs + (TILE_LAST + 1) * 8, 0, (255 - TILE_LAST) * 8);
    VIC.bgcolor0 = TILESET_BG;
    VIC.bgcolor1 = TILESET_MC1;
    VIC.bgcolor2 = TILESET_MC2;
    VIC.ctrl2 |= 0x10;                          /* multicolore, case par case (bit 3 de la Color RAM) */
    /* $D018 : bits 4-7 = écran / 1 Ko, bits 1-3 = jeu de caractères / 2 Ko,
       dans la banque ; banque choisie par les bits 0-1 de $DD00 (0 = banque 3). */
    VIC.addr = (((TILESET_SCREEN & 0x3FFF) >> 6) & 0xF0) | (((TILESET_CHARSET & 0x3FFF) >> 10) & 0x0E);
    CIA2.pra &= 0xFC;
    *(unsigned char *)0x0288 = TILESET_SCREEN >> 8;    /* page écran du KERNAL */
    return 0;
}

/* panel_glyph : motif (8 octets, ligne du haut d'abord, bit 7 = pixel de
   gauche) du code écran `code` du panneau. Codes libres : tous sauf ceux du
   texte (PANEL_TEXT_CODE). */
#include <string.h>
#include "libc64.h"

void __fastcall__ panel_glyph(unsigned char code, const unsigned char *bits)
{
    memcpy(PANEL_CHARSET + code * 8, bits, 8);
}

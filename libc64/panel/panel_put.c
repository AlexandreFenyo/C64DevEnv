/* panel_put : pose le code écran `code` (texte ou graphique défini par
   panel_glyph) colonne x, ligne y du panneau. */
#include "libc64.h"

void __fastcall__ panel_put(unsigned char x, unsigned char y, unsigned char code)
{
    PANEL_SCREEN[(PANEL_ROW + y) * 40 + x] = code;
}

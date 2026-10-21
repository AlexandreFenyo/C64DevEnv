/* panel_color : couleur (0-15) de n cases à partir de la colonne x, ligne y
   du panneau (Color RAM ; panel_init les met toutes à la couleur du texte). */
#include <string.h>
#include "libc64.h"

void __fastcall__ panel_color(unsigned char x, unsigned char y, unsigned char n, unsigned char color)
{
    memset((unsigned char *)0xD800 + (PANEL_ROW + y) * 40 + x, color, n);
}

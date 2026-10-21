/* screen_colors : couleurs de la bordure ($D020) et du fond ($D021). */
#include <c64.h>
#include "libc64.h"

void __fastcall__ screen_colors(unsigned char border, unsigned char background)
{
    VIC.bordercolor = border;
    VIC.bgcolor0 = background;
}

/* sprite_show : couleur du sprite n ($D027+n) puis activation ($D015). */
#include <c64.h>
#include "libc64.h"

void __fastcall__ sprite_show(unsigned char n, unsigned char color)
{
    VIC.spr_color[n] = color;
    VIC.spr_ena |= (unsigned char)(1 << n);
}

/* sprite_hide : désactive le sprite n ($D015). */
#include <c64.h>
#include "libc64.h"

void __fastcall__ sprite_hide(unsigned char n)
{
    VIC.spr_ena &= (unsigned char)~(1 << n);
}

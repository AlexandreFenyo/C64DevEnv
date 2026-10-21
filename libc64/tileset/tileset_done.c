/* tileset_done : rend le jeu de caractères de la ROM (majuscules/minuscules,
   comme le runtime cc65) et coupe le mode multicolore. */
#include <c64.h>
#include "libc64.h"

void tileset_done(void)
{
    VIC.ctrl2 &= (unsigned char)~0x10;
    VIC.addr = (VIC.addr & 0xF1) | 0x06;        /* $1800 : ROM minuscules/majuscules */
}

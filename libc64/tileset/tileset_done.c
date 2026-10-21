/* tileset_done : rend la banque VIC 0, l'écran $0400, le jeu de caractères de
   la ROM (majuscules/minuscules, comme le runtime cc65), coupe le multicolore. */
#include <c64.h>
#include "libc64.h"

void tileset_done(void)
{
    VIC.ctrl2 &= (unsigned char)~0x10;
    CIA2.pra |= 0x03;                           /* banque 0 */
    VIC.addr = 0x16;                            /* écran $0400, ROM minuscules/majuscules $1800 */
    *(unsigned char *)0x0288 = 0x04;
}

/* sprite_load : copie le motif (63 octets) dans le bloc de 64 octets
   `block` et y fait pointer le sprite n (pointeurs en $07F8-$07FF, écran
   en $0400, banque VIC 0). */
#include <string.h>
#include "libc64.h"

void __fastcall__ sprite_load(unsigned char n, unsigned char block, const unsigned char *data)
{
    memcpy((void *)(block * 64u), data, 63);
    *(unsigned char *)(0x07F8 + n) = block;
}

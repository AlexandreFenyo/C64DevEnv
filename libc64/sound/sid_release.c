/* sid_release : ferme le gate de la voix 1 (la note entre en relâchement). */
#include <c64.h>
#include "libc64.h"

void sid_release(void)
{
    SID.v1.ctrl = 0x10;     /* triangle, gate fermé */
}

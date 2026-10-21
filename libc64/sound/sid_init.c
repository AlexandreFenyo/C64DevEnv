/* sid_init : registres du SID à zéro (voix muettes), volume 15. */
#include <c64.h>
#include <string.h>
#include "libc64.h"

void sid_init(void)
{
    memset((void *)&SID, 0, 24);
    SID.amp = 0x0F;
}

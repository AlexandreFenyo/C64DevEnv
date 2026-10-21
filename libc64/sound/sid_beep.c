/* sid_beep : note sur la voix 1, onde triangle, attaque rapide et déclin
   moyen (ADSR $09/$A8), gate ouvert. freq = fréquence en Hz * 17,03 (PAL),
   ex. 0x1D45 = 440 Hz. */
#include <c64.h>
#include "libc64.h"

void __fastcall__ sid_beep(unsigned int freq)
{
    SID.v1.freq = freq;
    SID.v1.ad = 0x09;
    SID.v1.sr = 0xA8;
    SID.v1.ctrl = 0x11;     /* triangle + gate */
}

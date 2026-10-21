/* screen_print : écrit une chaîne dans la mémoire écran ($0400), en codes
   écran (cc65 convertit les chaînes en PETSCII, l'écran attend des codes
   écran : conversion ici). Les couleurs (mémoire $D800) ne changent pas. */
#include "libc64.h"

#define SCREEN ((unsigned char *)0x0400)

void __fastcall__ screen_print(unsigned char x, unsigned char y, const char *s)
{
    unsigned char *p = SCREEN + y * 40 + x;
    unsigned char c;

    while ((c = *s++) != 0) {
        if (c >= 0x40 && c < 0x60) {
            c -= 0x40;              /* lettres : 'A' PETSCII $41 -> code écran 1 */
        } else if (c >= 0x60 && c < 0x80) {
            c -= 0x20;
        } else if (c >= 0xC0 && c < 0xFF) {
            c -= 0x80;
        } else if (c == 0xFF) {
            c = 0x5E;
        }
        *p++ = c;
    }
}

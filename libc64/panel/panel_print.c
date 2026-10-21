/* panel_print : écrit une chaîne dans le panneau (écran $F000, à partir de la
   ligne PANEL_ROW), en codes écran du jeu minuscules/majuscules (même
   conversion que screen_print). Les couleurs ne changent pas. */
#include "libc64.h"

void __fastcall__ panel_print(unsigned char x, unsigned char y, const char *s)
{
    unsigned char *p = PANEL_SCREEN + (PANEL_ROW + y) * 40 + x;
    unsigned char c;

    while ((c = *s++) != 0) {
        if (c >= 0x40 && c < 0x60) {
            c -= 0x40;              /* PETSCII $41 'a' -> code écran 1 */
        } else if (c >= 0x60 && c < 0x80) {
            c -= 0x20;
        } else if (c >= 0xC0 && c < 0xFF) {
            c -= 0x80;              /* PETSCII $C1 'A' -> code écran $41 */
        } else if (c == 0xFF) {
            c = 0x5E;
        }
        *p++ = c;
    }
}

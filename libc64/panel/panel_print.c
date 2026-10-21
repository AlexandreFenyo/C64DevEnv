/* panel_print : écrit une chaîne dans le panneau (écran $F000, à partir de la
   ligne PANEL_ROW), en codes écran du jeu majuscules. Lettres (minuscules
   ou majuscules dans le source) -> A-Z (codes 1-26) ; chiffres, espace, « : »
   et « = » gardent leur code (PETSCII = code écran pour $20-$3F). Les autres
   caractères n'ont pas de motif (codes réservés aux graphiques). Les
   couleurs ne changent pas. */
#include "libc64.h"

void __fastcall__ panel_print(unsigned char x, unsigned char y, const char *s)
{
    unsigned char *p = PANEL_SCREEN + (PANEL_ROW + y) * 40 + x;
    unsigned char c;

    while ((c = *s++) != 0) {
        if (c >= 0x41 && c <= 0x5A) {
            c -= 0x40;              /* 'a' dans le source : PETSCII $41 -> 1 */
        } else if (c >= 0xC1 && c <= 0xDA) {
            c -= 0xC0;              /* 'A' dans le source : PETSCII $C1 -> 1 */
        }
        *p++ = c;
    }
}
